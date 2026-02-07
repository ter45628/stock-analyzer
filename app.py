import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- การตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Ultimate Stock Pro v2", layout="wide")

# --- ฟังก์ชันคำนวณ (รวม Indicators ทั้งหมด) ---
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
    hl2 = (high + low) / 2
    atr = (high - low).rolling(window=period).mean() # ATR แบบง่าย
    upper = hl2 + (multiplier * atr)
    lower = hl2 - (multiplier * atr)
    st_val = pd.Series(index=close.index, dtype=float)
    dir_val = pd.Series(index=close.index, dtype=int)
    for i in range(1, len(close)):
        if close.iloc[i] > (st_val.iloc[i-1] if not np.isnan(st_val.iloc[i-1]) else 0):
            st_val.iloc[i] = lower.iloc[i]
            dir_val.iloc[i] = 1
        else:
            st_val.iloc[i] = upper.iloc[i]
            dir_val.iloc[i] = -1
    return st_val, dir_val

def get_levels(df, window=15):
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

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["📉 วิเคราะห์เทคนิค", "📰 ข่าวสาร", "🔍 สแกนหุ้น"])

# --- โหลดข้อมูลหลัก ---
try:
    stock = yf.Ticker(ticker)
    data = stock.history(period="2y", interval=interval)
    
    if data.empty:
        st.error(f"ไม่พบข้อมูลสำหรับ {ticker}")
    else:
        # คำนวณ Indicators
        data['EMA50'] = calculate_ema(data['Close'], 50)
        data['EMA200'] = calculate_ema(data['Close'], 200)
        data['RSI'] = calculate_rsi(data['Close'], 14)
        data['MACD'], data['Signal'], data['Hist'] = calculate_macd(data['Close'])
        data['ST'], data['ST_Dir'] = calculate_supertrend(data['High'], data['Low'], data['Close'])
        
        # Squeeze Logic
        sma20 = data['Close'].rolling(window=20).mean()
        std20 = data['Close'].rolling(window=20).std()
        atr20 = (data['High'] - data['Low']).rolling(window=20).mean()
        data['Squeeze'] = ((sma20 + 2*std20) < (sma20 + 1.5*atr20))

        with tab1:
            st.title(f"📊 {ticker} Analysis")
            # กราฟ 3 Rows พร้อมปุ่มซูมที่ใช้ง่าย
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.6, 0.2, 0.2])
            fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Price"), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['EMA50'], name="EMA 50", line=dict(color='yellow', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['EMA200'], name="EMA 200", line=dict(color='orange', width=1.2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['ST'], name="Supertrend", line=dict(color='cyan', dash='dot')), row=1, col=1)
            
            levels = get_levels(data)
            for d, v, l in levels[-10:]:
                fig.add_hline(y=float(v), line_dash="dash", line_color="red" if l == 'Resistance' else "green", opacity=0.3)

            fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], name="RSI", line=dict(color='purple')), row=2, col=1)
            fig.add_trace(go.Bar(x=data.index, y=data['Hist'], name="MACD Hist"), row=3, col=1)

            fig.update_xaxes(rangeslider_visible=False, rangeselector=dict(buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(step="all", label="ALL")
            ])))
            fig.update_layout(height=800, template="plotly_dark", hovermode='x unified', dragmode='pan')
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("📰 ข่าวล่าสุด")
            # แก้ไขระบบดึงข่าวให้เสถียรขึ้น
            news = stock.news
            if not news:
                st.warning("ไม่พบข่าวสารจาก yfinance ลองเช็คชื่อ Ticker หรือรอสักครู่")
            else:
                for n in news[:10]:
                    with st.container():
                        # ใช้ .get() เพื่อป้องกันแอปพังถ้าข้อมูลไม่ครบ
                        st.markdown(f"### [{n.get('title', 'N/A')}]({n.get('link', '#')})")
                        tickers = n.get('relatedTickers', [])
                        if tickers: st.markdown(" ".join([f"`#{t}`" for t in tickers]))
                        st.write(f"*{n.get('publisher', 'Unknown')}* | {pd.to_datetime(n.get('providerPublishTime', 0), unit='s')}")
                        st.divider()

        with tab3:
            st.subheader("🔍 ระบบสแกนหาหุ้นใกล้แนวรับ (S&P 100)")
            # ขยาย Watchlist ให้กว้างขึ้นเพื่อโอกาสเจอผลลัพธ์
            watch = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX", "AMD", "DIS", "NKE", "BA", "V", "MA", "PYPL"]
            threshold = st.slider("ระยะห่างจากแนว (%)", 0.5, 5.0, 2.5) / 100
            
            if st.button("🚀 เริ่มการสแกน"):
                results = []
                bar = st.progress(0)
                table = st.empty()
                for i, s in enumerate(watch):
                    try:
                        sd = yf.download(s, period="6mo", progress=False)
                        if sd.empty: continue
                        # แก้ปัญหา MultiIndex ที่ทำให้หาค่าไม่เจอ
                        if isinstance(sd.columns, pd.MultiIndex): sd.columns = sd.columns.get_level_values(0)
                        cp = float(sd['Close'].iloc[-1])
                        lvls = get_levels(sd)
                        for _, v, l in lvls[-5:]:
                            if abs(cp - v) / cp <= threshold:
                                results.append({"Ticker": s, "Price": f"${cp:.2f}", "Status": f"Near {l}", "Level": f"${v:.2f}"})
                                table.table(pd.DataFrame(results))
                                break
                    except: continue
                    bar.progress((i + 1) / len(watch))
                if not results: st.info("ไม่พบหุ้นที่ตรงเงื่อนไข ลองเพิ่มค่า %")

except Exception as e:
    st.error(f"Error: {e}")
