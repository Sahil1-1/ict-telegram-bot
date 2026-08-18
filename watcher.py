import requests
import time
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

RAILWAY_URL = "https://ict-telegram-bot-production.up.railway.app"
WEBHOOK_SECRET = "ICTSahil2024Key987"
CHECK_INTERVAL = 60
COOLDOWN_HOURS = 4
ENFORCE_KILLZONE = False  # False = get signals anytime for testing, True = strict ICT

WATCHLIST = [
    {"symbol": "EURUSD", "yf_symbol": "EURUSD=X", "asset_class": "FOREX", "timeframe": "15", "exchange": "OANDA"},
    {"symbol": "GBPUSD", "yf_symbol": "GBPUSD=X", "asset_class": "FOREX", "timeframe": "15", "exchange": "OANDA"},
    {"symbol": "XAUUSD", "yf_symbol": "GC=F", "asset_class": "FOREX", "timeframe": "5", "exchange": "OANDA"},
    {"symbol": "NAS100", "yf_symbol": "^NDX", "asset_class": "INDEX", "timeframe": "60", "exchange": "CAPITALCOM"},
    {"symbol": "BTCUSDT", "yf_symbol": "BTC-USD", "asset_class": "CRYPTO", "timeframe": "5", "exchange": "BINANCE", "is_crypto": True, "binance": "BTCUSDT"},
    {"symbol": "ETHUSDT", "yf_symbol": "ETH-USD", "asset_class": "CRYPTO", "timeframe": "5", "exchange": "BINANCE", "is_crypto": True, "binance": "ETHUSDT"},
]

last_signals = {}

def is_killzone():
    try:
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)
        h = now.hour + now.minute/60.0
        in_london = 2 <= h < 5
        in_ny_am = 8.5 <= h < 11
        in_ny_pm = 13.5 <= h < 16
        return (in_london or in_ny_am or in_ny_pm)
    except:
        return True

def calc_atr(df, period=14):
    try:
        hl = df['High'] - df['Low']
        hc = (df['High'] - df['Close'].shift()).abs()
        lc = (df['Low'] - df['Close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(period).mean()
    except:
        return pd.Series([0]*len(df))

def get_yf(yf_symbol, timeframe):
    try:
        interval_map = {"5": "5m", "15": "15m", "60": "60m"}
        interval = interval_map.get(timeframe, "15m")
        period = "5d" if interval in ["5m","15m"] else "1mo"
        data = yf.download(yf_symbol, period=period, interval=interval, progress=False, auto_adjust=False)
        if data.empty or len(data) < 50:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = data.dropna()
        # Rename to standard
        data.columns = [c.title() for c in data.columns]
        return data
    except Exception as e:
        print(f"yf error {yf_symbol}: {e}")
        return None

def get_binance(symbol, timeframe):
    try:
        tf_map = {"5": "5m", "15": "15m", "60": "1h"}
        interval = tf_map.get(timeframe, "15m")
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list) or len(r) < 50:
            return None
        df = pd.DataFrame(r, columns=['ot','Open','High','Low','Close','Volume','ct','qav','trades','tb','tq','ig'])
        df = df[['Open','High','Low','Close','Volume']].astype(float)
        return df
    except Exception as e:
        print(f"binance error {symbol}: {e}")
        return None

def detect(df, info):
    try:
        if df is None or len(df) < 30:
            return None
        close = float(df['Close'].iloc[-1])
        high = float(df['High'].iloc[-1])
        low = float(df['Low'].iloc[-1])
        open_ = float(df['Open'].iloc[-1])

        df['ATR'] = calc_atr(df, 14)
        atr = float(df['ATR'].iloc[-1])
        if np.isnan(atr) or atr == 0:
            atr = float((df['High'] - df['Low']).tail(14).mean())

        body = abs(close - open_)
        avg_body = float(abs(df['Close'] - df['Open']).tail(10).mean())
        if avg_body == 0:
            return None

        # Find last swing high/low
        SL = 5
        last_high = None
        last_low = None
        last_high_idx = None
        last_low_idx = None
        for i in range(len(df)-SL-1, SL, -1):
            if df['High'].iloc[i] == df['High'].iloc[i-SL:i+SL+1].max() and last_high is None:
                last_high = float(df['High'].iloc[i])
                last_high_idx = i
            if df['Low'].iloc[i] == df['Low'].iloc[i-SL:i+SL+1].min() and last_low is None:
                last_low = float(df['Low'].iloc[i])
                last_low_idx = i
            if last_high and last_low:
                break

        if last_high is None or last_low is None:
            return None

        # Bias
        ema200 = float(df['Close'].ewm(span=200).mean().iloc[-1]) if len(df)>=200 else float(df['Close'].ewm(span=50).mean().iloc[-1])
        bias = 1 if close > ema200 else -1

        # Sweep
        bullish_sweep = low < last_low and close > last_low
        bearish_sweep = high > last_high and close < last_high

        if not bullish_sweep and not bearish_sweep:
            return None

        candle_range = high - low
        condA = body > 2.0 * avg_body
        condB = candle_range > 1.5 * atr
        if not (condA and condB):
            return None

        high2 = float(df['High'].iloc[-3])
        low2 = float(df['Low'].iloc[-3])
        bullish_fvg = (high2 < low) and ((low - high2) >= 0.5 * atr)
        bearish_fvg = (low2 > high) and ((low2 - high) >= 0.5 * atr)

        bullish_mss = bullish_sweep and close > last_high and bullish_fvg and bias == 1
        bearish_mss = bearish_sweep and close < last_low and bearish_fvg and bias == -1

        if not bullish_mss and not bearish_mss:
            return None

        is_long = bullish_mss
        if is_long:
            fvg_ce = (high2 + low) / 2
            entry = fvg_ce
            sl = float(df['Low'].tail(5).min()) - atr*0.2
            risk = entry - sl
            if risk <= 0: return None
            tp1 = entry + 2*risk
            tp2 = entry + 4*risk
            sig = "LONG"
        else:
            fvg_ce = (low2 + high) / 2
            entry = fvg_ce
            sl = float(df['High'].tail(5).max()) + atr*0.2
            risk = sl - entry
            if risk <= 0: return None
            tp1 = entry - 2*risk
            tp2 = entry - 4*risk
            sig = "SHORT"

        tf_display = f"{info['timeframe']}M" if int(info['timeframe'])<60 else f"{int(int(info['timeframe'])/60)}H"

        return {
            "secret": WEBHOOK_SECRET,
            "signal": sig,
            "symbol": info['symbol'],
            "asset_class": info['asset_class'],
            "broker": "Bitget" if info['asset_class']=="CRYPTO" else "IC Markets and CAPITAL.com",
            "crypto_type": "FUTURES" if info['asset_class']=="CRYPTO" else "",
            "timeframe": tf_display,
            "entry": round(entry,5),
            "stop_loss": round(sl,5),
            "tp1": round(tp1,5),
            "tp2": round(tp2,5),
            "rr_tp1": 2.0,
            "rr_tp2": 4.0,
            "confidence": "High Confidence",
            "risk_percent": 1.0,
            "exchange": info['exchange']
        }
    except Exception as e:
        print(f"detect error {info['symbol']}: {e}")
        return None

def should_send(symbol, sigtype):
    key = f"{symbol}_{sigtype}"
    now = datetime.now()
    if key in last_signals:
        diff_h = (now - last_signals[key]).total_seconds()/3600
        if diff_h < COOLDOWN_HOURS:
            print(f"Cooldown {symbol} {sigtype} {diff_h:.1f}h ago - SKIP")
            return False
    last_signals[key] = now
    return True

def send_signal(data):
    try:
        r = requests.post(f"{RAILWAY_URL}/webhook/tradingview", json=data, timeout=20)
        print(f"Sent {data['signal']} {data['symbol']} -> {r.status_code}")
    except Exception as e:
        print(f"send failed: {e}")

def run_watcher():
    print("=== ICT ELITE V3 Watcher - No Spam Mode Started ===")
    while True:
        try:
            in_kz = is_killzone()
            if ENFORCE_KILLZONE and not in_kz:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Outside Killzone - sleep 60s")
                time.sleep(60)
                continue

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning {len(WATCHLIST)} pairs...")
            for info in WATCHLIST:
                try:
                    df = get_binance(info['binance'], info['timeframe']) if info.get('is_crypto') else get_yf(info['yf_symbol'], info['timeframe'])
                    if df is None: 
                        continue
                    signal = detect(df, info)
                    if signal:
                        print(f"!!! FOUND ICT SETUP: {signal['signal']} {signal['symbol']}")
                        if should_send(signal['symbol'], signal['signal']):
                            send_signal(signal)
                            time.sleep(2)
                    else:
                        print(f"No setup: {info['symbol']}")
                    time.sleep(1)
                except Exception as e:
                    print(f"Error {info['symbol']}: {e}")
                    continue
            print("Scan done. Next in 60s - Expect 1-3 signals per day max")
            time.sleep(60)
        except Exception as e:
            print(f"Watcher loop error {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_watcher()
