import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- การตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="PRO US Stock Analyzer", layout="wide")

# --- ฟังก์ชันหาแนวรับแนวต้าน ---
def get_levels(df, window=20):
    levels = []
    for i in range(window, len(df) - window):
        if df['High'].iloc[i] == max(df['High'].iloc[i-window:i+window]):
            levels.append((df.index[i], df['High'].iloc[i], 'Resistance'))
        if df['Low'].iloc[i] == min(df['Low'].iloc[i-window:i+window]):
            levels.append((df.index[i], df['Low'].iloc[i], 'Support'))
    return levels

# --- ส่วน Sidebar ---
st.sidebar.header("🔍 ค้นหาหุ้น & ตั้งค่า")
ticker = st.sidebar.text_input("ชื่อหุ้น (Ticker Symbol)", value="NVDA").upper()
interval = st.sidebar.selectbox("Timeframe", ["1d", "1h", "15m", "5m"], index=0)

# ส่วน Risk Management ใน Sidebar
st.sidebar.markdown("---")
st.sidebar.header("🧮 Risk Management")
capital = st.sidebar.number_input("เงินทุนทั้งหมด ($)", value=10000.0)
risk_percent = st.sidebar.slider("ความเสี่ยงที่รับได้ (%)", 0.5, 5.0, 2.0) / 100

if ticker:
    try:
        # ดึงข้อมูล
        data = yf.download(ticker, period="2y", interval=interval)
        if data.empty:
            st.error("ไม่พบข้อมูลหุ้น โปรดตรวจสอบชื่อ Ticker อีกครั้ง")
        else:
            # --- คำนวณ Indicators ---
            data['EMA50'] = ta.ema(data['Close'], length=50)
            data['EMA200'] = ta.ema(data['Close'], length=200)
            data['RSI'] = ta.rsi(data['Close'], length=14)
            macd = ta.macd(data['Close'])
            data = pd.concat([data, macd], axis=1)
            st_df = ta.supertrend(data['High'], data['Low'], data['Close'], length=7, multiplier=3)
            data = pd.concat([data, st_df], axis=1)
            
            # Squeeze Momentum (Basic)
            bb = ta.bbands(data['Close'], length=20, std=2)
            kc = ta.kc(data['High'], data['Low'], data['Close'], length=20)
            data['Squeeze'] = bb['BBU_20_2.0'] < kc['KCUe_20_1.5']

            last_row = data.iloc[-1]
            prev_row = data.iloc[-2]

            # --- ส่วนแสดงผลบนหน้าหลัก ---
            st.title(f"📈 วิเคราะห์หุ้น {ticker}")
            
            # ตารางสรุปสัญญาณ (Signal Table)
            st.subheader("📊 Signal Summary")
            signals = [
                ["Trend (EMA 50/200)", "Bullish" if last_row['EMA50'] > last_row['EMA200'] else "Bearish"],
                ["Momentum (RSI)", "Overbought" if last_row['RSI'] > 70 else ("Oversold" if last_row['RSI'] < 30 else "Neutral")],
                ["Pulse (MACD)", "Strong Buy" if last_row.iloc[-7] > 0 and prev_row.iloc[-7] <= 0 else "Neutral"],
                ["Supertrend", "Buy Mode" if last_row['Close'] > last_row.iloc[-4] else "Sell Mode"],
                ["Squeeze", "Squeezing" if last_row['Squeeze'] else "No Squeeze"]
            ]
            sig_df = pd.DataFrame(signals, columns=["Indicator", "Signal"])
            st.table(sig_df)

            # --- กราฟ Interactive ---
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])
            
            # Row 1: Candlestick + EMA + Supertrend + Levels
            fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Price"), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['EMA50'], name="EMA 50", line=dict(color='yellow')), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['EMA200'], name="EMA 200", line=dict(color='orange')), row=1, col=1)
            
            # วาดแนวรับแนวต้านล่าสุด
            levels = get_levels(data)
            for date, val, label in levels[-8:]:
                color = "red" if label == 'Resistance' else "green"
                fig.add_hline(y=val, line_dash="dash", line_color=color, opacity=0.3, row=1, col=1)

            # Row 2: RSI
            fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], name="RSI", line=dict(color='purple')), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

            # Row 3: MACD
            fig.add_trace(go.Bar(x=data.index, y=data.iloc[:, -7], name="MACD Hist"), row=3, col=1)
            
            fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            # --- Risk Calculator Logic ---
            st.sidebar.subheader("🎯 แผนการเทรด")
            stop_loss = st.sidebar.number_input("จุดตัดขาดทุน (Stop Loss)", value=float(last_row['Low'] * 0.97))
            risk_amt = capital * risk_percent
            risk_per_sh = last_row['Close'] - stop_loss
            
            if risk_per_sh > 0:
                shares = int(risk_amt / risk_per_sh)
                st.sidebar.success(f"จำนวนหุ้นที่แนะนำ: {shares} หุ้น")
                st.sidebar.info(f"หากโดน SL จะขาดทุน: ${risk_amt:,.2f}")
            else:
                st.sidebar.warning("จุด SL ต้องต่ำกว่าราคาปัจจุบัน")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")
