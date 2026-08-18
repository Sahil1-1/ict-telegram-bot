import requests
import time
import json
from datetime import datetime

# ==========================================
# YOUR SETTINGS - DO NOT CHANGE THESE
# ==========================================
RAILWAY_URL    = "https://ict-telegram-bot-production.up.railway.app"
WEBHOOK_SECRET = "ICTSahil2024Key987"
CHECK_INTERVAL = 60  # Check every 60 seconds

# ==========================================
# YOUR TRADINGVIEW SYMBOLS TO WATCH
# Add or remove symbols as you need
# ==========================================
WATCHLIST = [
    # FOREX
    {"symbol": "EURUSD",  "asset_class": "FOREX",  "timeframe": "15"},
    {"symbol": "GBPUSD",  "asset_class": "FOREX",  "timeframe": "15"},
    {"symbol": "XAUUSD",  "asset_class": "FOREX",  "timeframe": "5"},
    {"symbol": "USDJPY",  "asset_class": "FOREX",  "timeframe": "15"},
    {"symbol": "GBPJPY",  "asset_class": "FOREX",  "timeframe": "15"},
    {"symbol": "AUDUSD",  "asset_class": "FOREX",  "timeframe": "15"},
    # INDICES
    {"symbol": "NAS100",  "asset_class": "INDEX",  "timeframe": "60"},
    {"symbol": "US30",    "asset_class": "INDEX",  "timeframe": "60"},
    {"symbol": "US500",   "asset_class": "INDEX",  "timeframe": "60"},
    {"symbol": "GER40",   "asset_class": "INDEX",  "timeframe": "60"},
    # CRYPTO
    {"symbol": "BTCUSDT", "asset_class": "CRYPTO", "timeframe": "5"},
    {"symbol": "ETHUSDT", "asset_class": "CRYPTO", "timeframe": "5"},
    {"symbol": "SOLUSDT", "asset_class": "CRYPTO", "timeframe": "5"},
]

# ==========================================
# TRADINGVIEW SCREENER
# ==========================================
SCREENER_URL = "https://scanner.tradingview.com/symbol"

FOREX_FIELDS = [
    "open", "high", "low", "close",
    "EMA20", "EMA50", "EMA200",
    "RSI", "MACD.macd", "MACD.signal",
    "Pivot.M.Classic.R1", "Pivot.M.Classic.S1",
    "Recommend.All", "Recommend.MA",
    "change", "change_abs",
    "volume", "ATR",
]

# Track last signal to avoid duplicates
last_signals = {}


def get_tradingview_data(symbol: str, asset_class: str, timeframe: str) -> dict:
    """Get real time data from TradingView screener."""
    try:
        # Determine screener based on asset class
        if asset_class == "FOREX":
            screener = "forex"
            exchange = "FX_IDC"
        elif asset_class == "INDEX":
            screener = "america"
            exchange = "CAPITALCOM"
        elif asset_class == "CRYPTO":
            screener = "crypto"
            exchange = "BINANCE"
        else:
            screener = "forex"
            exchange = "FX_IDC"

        url = f"https://scanner.tradingview.com/symbol"
        params = {
            "symbol"   : f"{exchange}:{symbol}",
            "fields"   : ",".join(FOREX_FIELDS),
            "no_404"   : "true",
        }

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer"   : "https://www.tradingview.com/",
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 200:
            return response.json()
        return {}

    except Exception as e:
        print(f"Error getting data for {symbol}: {e}")
        return {}


def detect_signal(data: dict, symbol: str, asset_class: str, timeframe: str) -> dict:
    """
    Analyze the data and detect if there is a trading signal.
    Uses EMA, RSI and MACD for signal detection.
    """
    try:
        if not data:
            return {}

        close      = data.get("close", 0)
        ema20      = data.get("EMA20", 0)
        ema50      = data.get("EMA50", 0)
        ema200     = data.get("EMA200", 0)
        rsi        = data.get("RSI", 50)
        macd       = data.get("MACD.macd", 0)
        macd_sig   = data.get("MACD.signal", 0)
        recommend  = data.get("Recommend.All", 0)
        atr        = data.get("ATR", 0)
        high       = data.get("high", 0)
        low        = data.get("low", 0)

        if not close or not ema20 or not ema50:
            return {}

        # ── LONG CONDITIONS ───────────────────────────────────────────
        long_conditions = (
            close > ema20 and          # Price above EMA20
            ema20 > ema50 and          # EMA20 above EMA50
            rsi > 50 and rsi < 70 and  # RSI in bullish zone
            macd > macd_sig and        # MACD bullish crossover
            recommend > 0.1            # TradingView recommends buy
        )

        # ── SHORT CONDITIONS ──────────────────────────────────────────
        short_conditions = (
            close < ema20 and          # Price below EMA20
            ema20 < ema50 and          # EMA20 below EMA50
            rsi < 50 and rsi > 30 and  # RSI in bearish zone
            macd < macd_sig and        # MACD bearish crossover
            recommend < -0.1           # TradingView recommends sell
        )

        if not long_conditions and not short_conditions:
            return {}

        signal_type = "LONG" if long_conditions else "SHORT"

        # Calculate entry, SL and TP
        atr_val = atr if atr > 0 else (close * 0.001)

        if signal_type == "LONG":
            entry     = close
            stop_loss = low - (atr_val * 1.5)
            tp1       = entry + (abs(entry - stop_loss) * 2)
            tp2       = entry + (abs(entry - stop_loss) * 4)
        else:
            entry     = close
            stop_loss = high + (atr_val * 1.5)
            tp1       = entry - (abs(stop_loss - entry) * 2)
            tp2       = entry - (abs(stop_loss - entry) * 4)

        risk       = abs(entry - stop_loss)
        rr_tp1     = round(abs(tp1 - entry) / risk, 2) if risk > 0 else 2.0
        rr_tp2     = round(abs(tp2 - entry) / risk, 2) if risk > 0 else 4.0

        # Determine broker
        if asset_class == "CRYPTO":
            broker      = "Bitget"
            crypto_type = "FUTURES" if int(timeframe) <= 60 else "SPOT"
            exchange    = "BITGET"
        else:
            broker      = "IC Markets and CAPITAL.com"
            crypto_type = ""
            exchange    = "OANDA" if asset_class == "FOREX" else "CAPITALCOM"

        # Format timeframe display
        tf_int = int(timeframe)
        if tf_int < 60:
            tf_display = f"{tf_int}M"
        elif tf_int == 60:
            tf_display = "1H"
        elif tf_int == 240:
            tf_display = "4H"
        else:
            tf_display = f"{tf_int}M"

        return {
            "secret"      : WEBHOOK_SECRET,
            "signal"      : signal_type,
            "symbol"      : symbol,
            "asset_class" : asset_class,
            "broker"      : broker,
            "crypto_type" : crypto_type,
            "timeframe"   : tf_display,
            "entry"       : round(entry, 5),
            "stop_loss"   : round(stop_loss, 5),
            "tp1"         : round(tp1, 5),
            "tp2"         : round(tp2, 5),
            "rr_tp1"      : rr_tp1,
            "rr_tp2"      : rr_tp2,
            "confidence"  : "Normal",
            "risk_percent": 1.0,
            "exchange"    : exchange,
        }

    except Exception as e:
        print(f"Error detecting signal for {symbol}: {e}")
        return {}


def send_signal(signal_data: dict) -> bool:
    """Send signal to Railway webhook server."""
    try:
        response = requests.post(
            f"{RAILWAY_URL}/webhook/tradingview",
            json=signal_data,
            timeout=30,
        )
        result = response.json()
        if result.get("status") == "success":
            print(f"Signal sent: {signal_data['signal']} {signal_data['symbol']}")
            return True
        print(f"Failed to send signal: {result}")
        return False
    except Exception as e:
        print(f"Error sending signal: {e}")
        return False


def should_send_signal(symbol: str, signal_type: str) -> bool:
    """
    Check if we already sent this signal recently.
    Prevents sending duplicate signals.
    """
    key = f"{symbol}_{signal_type}"
    now = datetime.now()

    if key in last_signals:
        last_time = last_signals[key]
        # Do not resend same signal within 4 hours
        diff = (now - last_time).total_seconds()
        if diff < 14400:
            return False

    last_signals[key] = now
    return True


def run_watcher():
    """Main loop that watches all symbols."""
    print("=" * 50)
    print("ICT Signal Watcher Started")
    print(f"Watching {len(WATCHLIST)} symbols")
    print(f"Checking every {CHECK_INTERVAL} seconds")
    print("=" * 50)

    while True:
        print(f"\nChecking signals at {datetime.now().strftime('%H:%M:%S')}...")

        for item in WATCHLIST:
            symbol      = item["symbol"]
            asset_class = item["asset_class"]
            timeframe   = item["timeframe"]

            try:
                # Get data
                data = get_tradingview_data(symbol, asset_class, timeframe)

                if not data:
                    print(f"No data for {symbol}")
                    continue

                # Detect signal
                signal = detect_signal(data, symbol, asset_class, timeframe)

                if not signal:
                    print(f"No signal for {symbol}")
                    continue

                # Check for duplicates
                if not should_send_signal(symbol, signal["signal"]):
                    print(f"Duplicate signal skipped for {symbol}")
                    continue

                # Send signal
                print(f"SIGNAL FOUND: {signal['signal']} {symbol}")
                send_signal(signal)

                # Wait 2 seconds between signals
                time.sleep(2)

            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                continue

        print(f"Scan complete. Next scan in {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_watcher()
