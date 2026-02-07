import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- การตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="PRO US Stock Analyzer", layout="wide")

# --- ฟังก์ชันคำนวณ Indicators ---
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
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(data, period=20, std=2):
    sma = data.rolling(window=period).mean()
    rolling_std = data.rolling(window=period).std()
    upper_band = sma + (rolling_std * std)
    lower_band = sma - (rolling_std * std)
    return upper_band, sma, lower_band

def calculate_supertrend(high, low, close, period=7, multiplier=3):
    hl_avg = (high + low) / 2
    atr = (high - low).rolling(window=period).mean()
    upper_band = hl_avg + (multiplier * atr)
    lower_band = hl_avg - (multiplier * atr)
    
    supertrend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)
    
    supertrend.iloc[0] = lower_band.iloc[0]
    direction.iloc[0] = 1
    
    for i in range(1, len(close)):
        if close.iloc[i] > supertrend.iloc[i-1]:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
        elif close.iloc[i] < supertrend.iloc[i-1]:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1
        else:
            supertrend.iloc[i] = supertrend.iloc[i-1]
            direction.iloc[i] = direction.iloc[i-1]
    return supertrend, direction

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

st.sidebar.markdown("---")
st.sidebar.header("🧮 Risk Management")
capital = st.sidebar.number_input("เงินทุนทั้งหมด ($)", value=10000.0)
risk_percent = st.sidebar.slider("ความเสี่ยงที่รับได้ (%)", 0.5, 5.0, 2.0) / 100

if ticker:
    try:
        # ปรับการดึงข้อมูลเพื่อป้องกัน Error จาก yfinance รุ่นใหม่
        data = yf.download(ticker, period="2y", interval=interval, progress=False)
        
        if data.empty:
            st.error("ไม่พบข้อมูลหุ้น โปรดตรวจสอบชื่อ Ticker อีกครั้ง")
        else:
            # แปลง MultiIndex เป็น Single Column ถ้าจำเป็น (ป้องกันกรณี yfinance คืนค่าแบบซับซ้อน)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            # --- คำนวณ Indicators ---
            data['EMA50'] = calculate_ema(data['Close'], 50)
            data['EMA200'] = calculate_ema(data['Close'], 200)
            data['RSI'] = calculate_rsi(data['Close'], 14)
            
            macd_line, signal_line, histogram = calculate_macd(data['Close'])
            data['MACD'] = macd_line
            data['MACD_Signal'] = signal_line
            data['MACD_Hist'] = histogram
            
            supertrend, direction = calculate_supertrend(data['High'], data['Low'], data['Close'])
            data['Supertrend'] = supertrend
            data['ST_Direction'] = direction
            
            bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(data['Close'])
            atr = (data['High'] - data['Low']).rolling(window=20).mean()
            kc_upper = bb_middle + (1.5 * atr)
            kc_lower = bb_middle - (1.5 * atr)
            data['Squeeze'] = (bb_upper < kc_upper) & (bb_lower > kc_lower)

            # ดึงค่าล่าสุดแบบ Scalar (ใช้ .item() เพื่อป้องกัน Series Error)
            last_close = float(data['Close'].iloc[-1])
            prev_close = float(data['Close'].iloc[-2])
            last_rsi = float(data['RSI'].iloc[-1])
            last_ema50 = float(data['EMA50'].iloc[-1])
            last_ema200 = float(data['EMA200'].iloc[-1])
            last_macd_hist = float(data['MACD_Hist'].iloc[-1])
            prev_macd_hist = float(data['MACD_Hist'].iloc[-2])
            last_st_dir = int(data['ST_Direction'].iloc[-1])
            last_squeeze = bool(data['Squeeze'].iloc[-1])

            # --- ส่วนแสดงผลบนหน้าหลัก ---
            st.title(f"📈 วิเคราะห์หุ้น {ticker}")
            
            st.subheader("📊 Signal Summary")
            signals = [
                ["Trend (EMA 50/200)", "Bullish ✅" if last_ema50 > last_ema200 else "Bearish ❌"],
                ["Momentum (RSI)", "Overbought 🔴" if last_rsi > 70 else ("Oversold 🟢" if last_rsi < 30 else "Neutral ⚪")],
                ["Pulse (MACD)", "Strong Buy 🚀" if last_macd_hist > 0 and prev_macd_hist <= 0 else "Neutral ⚪"],
                ["Supertrend", "Buy Mode 🟢" if last_st_dir > 0 else "Sell Mode 🔴"],
                ["Squeeze", "Squeezing 💥" if last_squeeze else "No Squeeze ⚪"]
            ]
            sig_df = pd.DataFrame(signals, columns=["Indicator", "Signal"])
            st.table(sig_df)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("ราคาปัจจุบัน", f"${last_close:.2f}")
            with col2:
                change = last_close - prev_close
                change_pct = (change / prev_close) * 100
                st.metric("เปลี่ยนแปลง", f"${change:.2f}", f"{change_pct:.2f}%")
            with col3:
                st.metric("Volume", f"{int(data['Volume'].iloc[-1]):,}")
            with col4:
                st.metric("RSI", f"{last_rsi:.2f}")

            # --- กราฟ Interactive ---
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])
            fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name="Price"), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['EMA50'], name="EMA 50", line=dict(color='yellow', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['EMA200'], name="EMA 200", line=dict(color='orange', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['Supertrend'], name="Supertrend", line=dict(color='purple', width=1, dash='dash')), row=1, col=1)
            
            levels = get_levels(data)
            for date, val, label in levels[-8:]:
                color = "red" if label == 'Resistance' else "green"
                fig.add_hline(y=float(val), line_dash="dash", line_color=color, opacity=0.3, row=1, col=1)

            fig.add_trace(go.Scatter(x=data.index, y=data['RSI'], name="RSI", line=dict(color='purple', width=2)), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

            fig.add_trace(go.Bar(x=data.index, y=data['MACD_Hist'], name="MACD Hist", marker_color='lightblue'), row=3, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['MACD'], name="MACD", line=dict(color='blue', width=1)), row=3, col=1)
            fig.add_trace(go.Scatter(x=data.index, y=data['MACD_Signal'], name="Signal", line=dict(color='red', width=1)), row=3, col=1)
            
            fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False, showlegend=True, hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)

            # --- Risk Calculator Logic ---
            st.sidebar.subheader("🎯 แผนการเทรด")
            sl_default = float(data['Low'].iloc[-1] * 0.97)
            stop_loss = st.sidebar.number_input("จุดตัดขาดทุน (Stop Loss)", value=sl_default, format="%.2f")
            
            risk_amt = capital * risk_percent
            risk_per_sh = last_close - stop_loss
            
            if risk_per_sh > 0:
                shares = int(risk_amt / risk_per_sh)
                total_cost = shares * last_close
                st.sidebar.success(f"✅ จำนวนหุ้นที่แนะนำ: **{shares:,} หุ้น**")
                st.sidebar.info(f"💰 ใช้เงิน: **${total_cost:,.2f}**")
                st.sidebar.warning(f"⚠️ หากโดน SL จะขาดทุน: **${risk_amt:,.2f}**")
                
                tp_price = last_close + (2 * risk_per_sh)
                st.sidebar.success(f"🎯 Take Profit (R:R 1:2): **${tp_price:.2f}**")
            else:
                st.sidebar.error("❌ จุด SL ต้องต่ำกว่าราคาปัจจุบัน")

    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาด: {e}")
