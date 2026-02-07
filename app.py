import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- การตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Ultimate US Stock Analyzer", layout="wide")

# --- ฟังก์ชันคำนวณ Indicators (Core Logic) ---
def calculate_ema(data, period):
    return data.ewm(span=period, adjust=False).mean()

def calculate_rsi(data, period=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data, fast=12, slow=26, signal=9):
    ema_fast = data.ewm(span=fast, adjust=False).mean()
    ema_slow = data.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line

def calculate_supertrend(high, low, close, period=7, multiplier=3):
    hl_avg = (high + low) / 2
    atr = (high - low).rolling(window=period).mean() # Simplified ATR
    upper_band = hl_avg + (multiplier * atr)
    lower_band = hl_avg - (multiplier * atr)
    supertrend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)
    for i in range(1, len(close)):
        if close.iloc[i] > (supertrend.iloc[i-1] if not np.isnan(supertrend.iloc[i-1]) else 0):
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
        else:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1
    return supertrend, direction

def get_levels(df, window=20):
    levels = []
    for i in range(window, len(df) - window):
        if df['High'].iloc[i] == max(df['High'].iloc[i-window:i+window]):
            levels.append((df.index[i], df['High'].iloc[i], 'Resistance'))
        if df['Low'].iloc[i] == min(df['Low'].iloc[i-window:i+window]):
            levels.append((df.index[i], df['Low'].iloc[i], 'Support'))
    return levels

# --- Sidebar ---
st.sidebar.title("🚀 Navigation")
ticker = st.sidebar.text_input("Ticker Symbol", value="NVDA").upper()
interval = st.sidebar.selectbox("Timeframe", ["1d", "1h", "15m", "5m"], index=0)

st.sidebar.markdown("---")
st.sidebar.header("🧮 Risk Management")
capital = st.sidebar.number_input("เงินทุนทั้งหมด ($)", value=10000.0)
risk_percent = st.sidebar.slider("ความเสี่ยงที่รับได้ (%)", 0.5, 5.0, 2.0) / 100

# --- Main Page Tabs ---
tab1, tab2, tab3 = st.tabs(["📉 วิเคราะห์เทคนิค", "📰 ข่าวสาร & Tags", "🔍 สแกนหุ้น (Screener)"])

# ดึงข้อมูลหลัก
data = yf.download(ticker, period="2y", interval=interval, progress=False)
if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)

if not data.empty:
    # คำนวณ Indicators
    data['EMA50'] = calculate_ema(data['Close'], 50)
    data['EMA200'] = calculate_ema(data['Close'], 200)
    data['RSI'] = calculate_rsi(data['Close'], 14)
    data['MACD'], data['Signal'], data['Hist'] = calculate_macd(data['Close'])
    data['ST'], data['ST_Dir'] = calculate_supertrend(data['High'], data['Low'], data['Close'])
    
    last_row = data.iloc[-1]
    
    with tab1:
        st.subheader(f"Technical Analysis: {ticker}")
        
        # กราฟหลัก
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])
        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Price"), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA50'], name="EMA 50", line=dict(color='yellow')), row=1, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data['EMA200'], name="EMA 200", line=dict(color='orange')), row=1, col=1)
        
        # แนวรับแนวต้าน
        levels = get_levels(data)
        for d, v, l in levels[-10:]:
            fig.add_hline(y=float(v), line_dash="dash", line_color="red" if l == 'Resistance' else "green", opacity=0.3)

        fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], name="RSI", line=dict(color='purple')), row=2, col=1)
        fig.add_trace(go.Bar(x=data.index, y=data['Hist'], name="MACD Hist"), row=3, col=1)
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # Risk Calculator in Sidebar
        sl_price = st.sidebar.number_input("Stop Loss Price", value=float(last_row['Low'] * 0.98))
        risk_amt = capital * risk_percent
        shares = int(risk_amt / (last_row['Close'] - sl_price)) if (last_row['Close'] - sl_price) > 0 else 0
        st.sidebar.success(f"✅ ซื้อได้: {shares} หุ้น")

    with tab2:
        st.subheader("📰 Market News & Related Tickers")
        news_list = yf.Ticker(ticker).news
        for news in news_list[:8]:
            col_t, col_i = st.columns([3, 1])
            with col_t:
                st.write(f"### [{news['title']}]({news['link']})")
                related = news.get('relatedTickers', [])
                if related:
                    st.markdown(" ".join([f"`#{t}`" for t in related]))
                st.write(f"*{news['publisher']}* | {pd.to_datetime(news['providerPublishTime'], unit='s')}")
            if 'thumbnail' in news:
                col_i.image(news['thumbnail']['resolutions'][0]['url'])
            st.divider()

    with tab3:
        st.subheader("🔍 Dynamic Support/Resistance Screener")
        mode = st.radio("เลือกกลุ่ม:", ["Tech Favorites", "S&P 100", "Custom"], horizontal=True)
        if mode == "Tech Favorites": stocks = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]
        elif mode == "S&P 100": stocks = pd.read_html('https://en.wikipedia.org/wiki/S%26P_100')[2]['Symbol'].tolist()
        else: stocks = st.text_input("Enter symbols (comma separated)", "AAPL,TSLA").split(",")
        
        dist_threshold = st.slider("ระยะห่างจากแนวรับ/ต้าน (%)", 0.1, 5.0, 1.0) / 100
        
        if st.button("🚀 Start Scan"):
            results = []
            p_bar = st.progress(0)
            table_spot = st.empty()
            for i, s in enumerate(stocks):
                try:
                    s = s.strip().upper()
                    s_data = yf.download(s, period="3mo", progress=False)
                    if isinstance(s_data.columns, pd.MultiIndex): s_data.columns = s_data.columns.get_level_values(0)
                    curr = float(s_data['Close'].iloc[-1])
                    s_lvls = get_levels(s_data)
                    for _, val, lbl in s_lvls[-5:]:
                        if abs(curr - val) / curr <= dist_threshold:
                            results.append({"Ticker": s, "Price": curr, "Status": f"Near {lbl}", "Level": val})
                            table_spot.table(pd.DataFrame(results))
                            break
                except: continue
                p_bar.progress((i + 1) / len(stocks))
