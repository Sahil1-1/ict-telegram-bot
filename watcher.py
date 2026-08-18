import requests
import time
import json
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

RAILWAY_URL = "https://ict-telegram-bot-production.up.railway.app"
WEBHOOK_SECRET = "ICTSahil2024Key987"
CHECK_INTERVAL = 60  # Check every 60 seconds

# --- ICT SETTINGS FROM YOUR PINE SCRIPT ---
SWING_LENGTH = 5
FVG_MIN_SIZE = 0.5
BODY_MULTIPLIER = 2.0
ATR_MULTIPLIER = 1.5
SWEEP_LOOKBACK = 50
COOLDOWN_HOURS = 4

WATCHLIST = [
    {"symbol": "EURUSD", "yf_symbol": "EURUSD=X", "asset_class": "FOREX", "timeframe": "15", "exchange": "OANDA"},
    {"symbol": "GBPUSD", "yf_symbol": "GBPUSD=X", "asset_class": "FOREX", "timeframe": "15", "exchange": "OANDA"},
    {"symbol": "XAUUSD", "yf_symbol": "GC=F", "asset_class": "FOREX", "timeframe": "5", "exchange": "OANDA"},
    {"symbol": "NAS100", "yf_symbol": "^NDX", "asset_class": "INDEX", "timeframe": "60", "exchange": "CAPITALCOM"},
    {"symbol": "US30", "yf_symbol": "^DJI", "asset_class": "INDEX", "timeframe": "60", "exchange": "CAPITALCOM"},
    {"symbol": "BTCUSDT", "yf_symbol": "BTC-USD", "asset_class": "CRYPTO", "timeframe": "5", "exchange": "BINANCE", "is_crypto": True, "binance": "BTCUSDT"},
    {"symbol": "ETHUSDT", "yf_symbol": "ETH-USD", "asset_class": "CRYPTO", "timeframe": "5", "exchange": "BINANCE", "is_crypto": True, "binance": "ETHUSDT"},
]

last_signals = {}

def is_killzone():
    try:
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)
        hour = now.hour + now.minute/60.0
        # London 2-5 AM, NY AM 8:30-11, NY PM 13:30-16 EST
        in_london = 2 <= hour < 5
        in_ny_am = 8.5 <= hour < 11
        in_ny_pm = 13.5 <= hour < 16
        # For testing outside killzone, allow but with lower confidence
        # Return True always for now but log it
        if in_london or in_ny_am or in_ny_pm:
            return True, True
        else:
            # Outside killzone = don't trade (ICT Rule)
            return False, False
    except:
        return True, True

def calculate_atr(df, period=14):
    try:
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(period).mean()
        return atr
    except:
        return pd.Series([0]*len(df))

def get_data_yf(yf_symbol, timeframe):
    try:
        # Map timeframe to yfinance interval
        tf_map = {"5": "5m", "15": "15m", "60": "60m", "240": "60m"}
        interval = tf_map.get(timeframe, "15m")
        period = "5d" if interval in ["5m", "15m"] else "1mo"
        
        data = yf.download(yf_symbol, period=period, interval=interval, progress=False, auto_adjust=False)
        if data.empty or len(data) < 50:
            return None
        # Flatten multi-index if needed
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = data.dropna()
        return data
    except Exception as e:
        print(f"yfinance error {yf_symbol}: {e}")
        return None

def get_data_binance(symbol, timeframe):
    try:
        tf_map = {"5": "5m", "15": "15m", "60": "1h", "240": "4h"}
        interval = tf_map.get(timeframe, "15m")
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) < 50:
            return None
        df = pd.DataFrame(r, columns=['open_time','Open','High','Low','Close','Volume','close_time','qav','trades','taker_base','taker_quote','ignore'])
        df = df[['Open','High','Low','Close','Volume']].astype(float)
        df.index = range(len(df))
        return df
    except Exception as e:
        print(f"Binance error {symbol}: {e}")
        return None

def detect_ict_signal(df, info):
    try:
        if df is None or len(df) < 30:
            return None
        
        # Ensure columns uppercase
        df.columns = [c.capitalize() if c.lower() in ['open','high','low','close','volume'] else c for c in df.columns]
        if 'Close' not in df.columns:
            # Try lowercase
            df.columns = [c.title() for c in df.columns]

        close = df['Close'].iloc[-1]
        high = df['High'].iloc[-1]
        low = df['Low'].iloc[-1]
        open_ = df['Open'].iloc[-1]
        
        prev_close = df['Close'].iloc[-2]
        prev_open = df['Open'].iloc[-2]
        
        # ATR
        df['ATR'] = calculate_atr(df, 14)
        atr = df['ATR'].iloc[-1]
        if pd.isna(atr) or atr == 0:
            atr = (df['High'] - df['Low']).tail(14).mean()
        
        # Body calculations
        body = abs(close - open_)
        avg_body = abs(df['Close'] - df['Open']).tail(10).mean()
        
        if avg_body == 0:
            return None

        # Find last swing high/low (simplified pivot)
        swing_len = SWING_LENGTH
        last_swing_high = None
        last_swing_low = None
        last_swing_high_idx = None
        last_swing_low_idx = None

        for i in range(len(df)-swing_len-1, swing_len, -1):
            window_high = df['High'].iloc[i-swing_len:i+swing_len+1].max()
            if df['High'].iloc[i] == window_high and last_swing_high is None:
                last_swing_high = df['High'].iloc[i]
                last_swing_high_idx = i
            window_low = df['Low'].iloc[i-swing_len:i+swing_len+1].min()
            if df['Low'].iloc[i] == window_low and last_swing_low is None:
                last_swing_low = df['Low'].iloc[i]
                last_swing_low_idx = i
            if last_swing_high and last_swing_low:
                break

        if last_swing_high is None or last_swing_low is None:
            return None

        # Bias - simple EMA bias like in your script
        ema50 = df['Close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['Close'].ewm(span=200).mean().iloc[-1] if len(df) >= 200 else ema50
        bias = 1 if close > ema200 else -1

        # --- BULLISH SWEEP DETECTION ---
        bullish_sweep = False
        bearish_sweep = False
        
        # Look back for sweep
        recent_lows = df['Low'].tail(SWEEP_LOOKBACK)
        recent_highs = df['High'].tail(SWEEP_LOOKBACK)
        
        # Bullish sweep: price went below last swing low then closed above it
        if low < last_swing_low and close > last_swing_low:
            # Check if sweep happened recently (within 10 bars)
            if len(df) - last_swing_low_idx <= SWEEP_LOOKBACK:
                bullish_sweep = True

        # Bearish sweep
        if high > last_swing_high and close < last_swing_high:
            if len(df) - last_swing_high_idx <= SWEEP_LOOKBACK:
                bearish_sweep = True

        if not bullish_sweep and not bearish_sweep:
            return None

        # --- DISPLACEMENT CHECK ---
        # Cond A: Body > bodyMultiplier * avgBody
        condA = body > BODY_MULTIPLIER * avg_body
        # Cond B: Range > atrMultiplier * ATR
        candle_range = high - low
        condB = candle_range > ATR_MULTIPLIER * atr
        # Cond C: Close beyond swing
        condC_bull = close > last_swing_high
        condC_bear = close < last_swing_low

        # --- FVG CHECK ---
        # Bullish FVG: high[2] < low (current)
        high_2 = df['High'].iloc[-3]
        low_2 = df['Low'].iloc[-3]
        
        bullish_gap = low - high_2
        bearish_gap = low_2 - high
        
        condD_bull = (high_2 < low) and (bullish_gap >= FVG_MIN_SIZE * atr)
        condD_bear = (low_2 > high) and (bearish_gap >= FVG_MIN_SIZE * atr)

        # Final MSS conditions
        bullish_mss = bullish_sweep and condA and condB and condC_bull and condD_bull and bias == 1
        bearish_mss = bearish_sweep and condA and condB and condC_bear and condD_bear and bias == -1

        if not bullish_mss and not bearish_mss:
            return None

        # --- CALCULATE ENTRY / SL / TP ---
        is_long = bullish_mss
        
        if is_long:
            fvg_top = high_2
            fvg_bottom = low
            fvg_ce = (fvg_top + fvg_bottom) / 2
            entry = fvg_ce
            sl = df['Low'].tail(5).min() - (atr * 0.2)  # Sweep candle low
            risk = entry - sl
            if risk <= 0:
                return None
            tp1 = entry + (2 * risk)
            tp2 = entry + (4 * risk)
            signal_type = "LONG"
        else:
            fvg_top = low_2
            fvg_bottom = high
            fvg_ce = (fvg_top + fvg_bottom) / 2
            entry = fvg_ce
            sl = df['High'].tail(5).max() + (atr * 0.2)
            risk = sl - entry
            if risk <= 0:
                return None
            tp1 = entry - (2 * risk)
            tp2 = entry - (4 * risk)
            signal_type = "SHORT"

        # Risk to reward
        rr1 = 2.0
        rr2 = 4.0

        return {
            "secret": WEBHOOK_SECRET,
            "signal": signal_type,
            "symbol": info["symbol"],
            "asset_class": info["asset_class"],
            "broker": "Bitget" if info["asset_class"] == "CRYPTO" else "IC Markets and CAPITAL.com",
            "crypto_type": "FUTURES" if info["asset_class"] == "CRYPTO" else "",
            "timeframe": f"{info['timeframe']}M" if int(info['timeframe']) < 60 else f"{int(int(info['timeframe'])/60)}H",
            "entry": round(float(entry), 5),
            "stop_loss": round(float(sl), 5),
            "tp1": round(float(tp1), 5),
            "tp2": round(float(tp2), 5),
            "rr_tp1": rr1,
            "rr_tp2": rr2,
            "confidence": "High Confidence",
            "risk_percent": 1.0,
            "exchange": info["exchange"]
        }

    except Exception as e:
        print(f"Detect error {info['symbol']}: {e}")
        return None

def should_send(symbol, signal_type):
    key = f"{symbol}_{signal_type}"
    now = datetime.now()
    if key in last_signals:
        diff = (now - last_signals[key]).total_seconds() / 3600
        if diff < COOLDOWN_HOURS:
            print(f"Cooldown active for {symbol} {signal_type} - {diff:.1f}h ago")
            return False
    last_signals[key] = now
    return True

def send_signal(data):
    try:
        r = requests.post(f"{RAILWAY_URL}/webhook/tradingview", json=data, timeout=20)
        print(f"Sent {data['signal']} {data['symbol']} -> {r.status_code}")
        return True
    except Exception as e:
        print(f"Send failed: {e}")
        return False

def run_watcher():
    print("="*50)
    print("ICT ELITE Watcher V2 Started - No Spam Mode")
    print("="*50)
    consecutive_errors = 0
    while True:
        try:
            in_kz, is_active = is_killzone()
            if not in_kz:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Outside Killzone - Sleeping 60s")
                time.sleep(60)
                continue

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning {len(WATCHLIST)} pairs for ICT setup...")

            for info in WATCHLIST:
                try:
                    df = None
                    if info.get("is_crypto"):
                        df = get_data_binance(info["binance"], info["timeframe"])
                    else:
                        df = get_data_yf(info["yf_symbol"], info["timeframe"])
                    
                    if df is None:
                        continue

                    signal = detect_ict_signal(df, info)
                    if signal:
                        print(f"!!! ICT SIGNAL FOUND: {signal['signal']} {signal['symbol']}")
                        if should_send(signal["symbol"], signal["signal"]):
                            send_signal(signal)
                            time.sleep(3)
                        else:
                            print("Skipped due to cooldown")
                    else:
                        print(f"No ICT setup: {info['symbol']}")

                    time.sleep(2)
                except Exception as e:
                    print(f"Error processing {info['symbol']}: {e}")
                    continue
            
            print(f"Scan complete. Next scan in {CHECK_INTERVAL}s. (Only 1-3 signals per day expected)")
            time.sleep(CHECK_INTERVAL)
            consecutive_errors = 0

        except Exception as e:
            consecutive_errors += 1
            print(f"Watcher loop error: {e} - Retry in 60s")
            time.sleep(60)
            if consecutive_errors > 10:
                time.sleep(300)

if __name__ == "__main__":
    run_watcher()
