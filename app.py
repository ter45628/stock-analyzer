import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- การตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Ultimate Stock Pro", layout="wide")

# --- ฟังก์ชันคำนวณ (Core logic) ---
def calculate_ema(data, period):
    return data.ewm(span=period, adjust=False).mean()

def calculate_rsi(data, period=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

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
ticker = st.sidebar.text_input("ชื่อหุ้น (Ticker Symbol)", value="NVDA").upper()
interval = st.sidebar.selectbox("Timeframe", ["1d", "1h", "15m", "5m"], index=0)

st.sidebar.markdown("---")
st.sidebar.header("🧮 Risk Management")
capital = st.sidebar.number_input("เงินทุนทั้งหมด ($)", value=10000.0)
risk_percent = st.sidebar.slider("ความเสี่ยงที่รับได้ (%)", 0.5, 5.0, 2.0) / 100

# --- Tabs หลัก ---
tab1, tab2, tab3 = st.tabs(["📉 วิเคราะห์เทคนิค", "📰 ข่าวสาร & Tags", "🔍 สแกนหุ้น (Screener)"])

# ดึงข้อมูลหลักสำหรับหน้าวิเคราะห์
try:
    data = yf.download(ticker, period="2y", interval=interval, progress=False)
    if not data.empty:
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        
        # คำนวณค่าเทคนิค
        data['EMA50'] = calculate_ema(data['Close'], 50)
        data['EMA200'] = calculate_ema(data['Close'], 200)
        data['RSI'] = calculate_rsi(data['Close'], 14)
        last_close = float(data['Close'].iloc[-1])

        with tab1:
            st.title(f"📈 วิเคราะห์หุ้น {ticker}")
            # กราฟ (ย่อส่วนจากเดิมเพื่อความเร็ว)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Price"), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['EMA50'], name="EMA 50", line=dict(color='yellow')), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], name="RSI", line=dict(color='purple')), row=2, col=1)
            
            levels = get_levels(data)
            for d, v, l in levels[-8:]:
                fig.add_hline(y=float(v), line_dash="dash", line_color="red" if l == 'Resistance' else "green", opacity=0.3)
            
            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            # Risk Calc
            sl_price = st.sidebar.number_input("Stop Loss Price", value=float(data['Low'].iloc[-1] * 0.98))
            risk_per_sh = last_close - sl_price
            if risk_per_sh > 0:
                shares = int((capital * risk_percent) / risk_per_sh)
                st.sidebar.success(f"✅ ซื้อได้: {shares} หุ้น")
            else: st.sidebar.error("SL ต้องต่ำกว่าราคาเข้า")

    with tab2:
        st.subheader(f"📰 ข่าวสารล่าสุดของ {ticker}")
        try:
            # แก้ไขจุด KeyError โดยใช้ .get() และตรวจสอบโครงสร้าง
            raw_news = yf.Ticker(ticker).news
            if not raw_news:
                st.info("ไม่พบข่าวสารในขณะนี้")
            else:
                for n in raw_news[:10]:
                    title = n.get('title', 'ไม่มีหัวข้อข่าว')
                    link = n.get('link', '#')
                    publisher = n.get('publisher', 'ไม่ทราบแหล่งข่าว')
                    pub_time = n.get('providerPublishTime', 0)
                    tickers = n.get('relatedTickers', [])
                    
                    with st.container():
                        st.markdown(f"### [{title}]({link})")
                        if tickers:
                            st.markdown(" ".join([f"`#{t}`" for t in tickers]))
                        st.write(f"*{publisher}* | {pd.to_datetime(pub_time, unit='s')}")
                        st.divider()
        except Exception as e:
            st.error(f"ไม่สามารถโหลดข่าวได้: {e}")

    with tab3:
        st.subheader("🔍 ระบบสแกนหาหุ้นใกล้แนวรับ/แนวต้าน")
        watch_list = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX", "AMD"]
        threshold = st.slider("ระยะห่างจากแนว (%)", 0.5, 3.0, 1.0) / 100

        if st.button("🚀 เริ่มการสแกน"):
            results = []
            bar = st.progress(0)
            status_text = st.empty()
            table_spot = st.empty()
            
            for i, s in enumerate(watch_list):
                try:
                    status_text.text(f"กำลังตรวจสอบ: {s}")
                    s_data = yf.download(s, period="3mo", progress=False)
                    if s_data.empty: continue
                    if isinstance(s_data.columns, pd.MultiIndex): s_data.columns = s_data.columns.get_level_values(0)
                    
                    curr_p = float(s_data['Close'].iloc[-1])
                    s_lvls = get_levels(s_data)
                    
                    for _, val, lbl in s_lvls[-5:]:
                        dist = abs(curr_p - val) / curr_p
                        if dist <= threshold:
                            results.append({"Ticker": s, "Price": f"${curr_p:.2f}", "Status": f"Near {lbl}", "Level": f"${val:.2f}"})
                            table_spot.table(pd.DataFrame(results))
                            break
                except: continue
                bar.progress((i + 1) / len(watch_list))
            status_text.text("✅ สแกนเสร็จสิ้น")

except Exception as e:
    st.error(f"เกิดข้อผิดพลาด: {e}")
