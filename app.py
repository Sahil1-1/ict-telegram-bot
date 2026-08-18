import json
import logging
import threading
import time

from flask import Flask, request, jsonify
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_SECRET, PORT
from signal_formatter import format_signal_message
from telegram_sender import broadcast_message, send_message, set_bot_commands, get_bot_info
from member_manager import handle_command
from database import save_signal, mark_signal_sent

# ==========================================
# LOGGING SETUP
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("ICT-Bot")

app = Flask(__name__)


# ==========================================
# ROUTES
# ==========================================

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "online", "service": "ICT Signal Bot"}), 200


@app.route("/webhook/tradingview", methods=["POST"])
def tradingview_webhook():
    try:
        raw  = request.get_data(as_text=True)
        data = json.loads(raw)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    header_secret = request.headers.get("X-Webhook-Secret", "")
    body_secret   = data.pop("secret", "")
    secret        = header_secret or body_secret

    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        logger.warning("Unauthorised webhook attempt")
        return jsonify({"error": "Unauthorized"}), 401

    signal_type = data.get("signal", "")
    valid       = {"LONG", "SHORT", "TP1_HIT", "TRADE_CLOSED"}
    if signal_type not in valid:
        return jsonify({"error": f"Invalid signal: {signal_type}"}), 400

    logger.info(
        f"Received: {signal_type} | {data.get('symbol')} | {data.get('timeframe')}"
    )

    asset_class         = data.get("asset_class", "FOREX").upper()
    data["asset_class"] = asset_class

    if asset_class == "CRYPTO":
        data["broker"] = "Bitget"
        if not data.get("crypto_type"):
            data["crypto_type"] = "FUTURES"
    else:
        data["broker"] = "IC Markets and CAPITAL.com"

    try:
        saved = save_signal(data, raw)
    except Exception as e:
        logger.error(f"DB error: {e}")
        saved = None

    try:
        message = format_signal_message(data)
    except Exception as e:
        logger.error(f"Format error: {e}")
        message = f"New {signal_type} signal for {data.get('symbol', 'N/A')}"

    results = broadcast_message(message)

    if saved and all(results.values()):
        mark_signal_sent(saved.id)

    return jsonify({
        "status": "success",
        "signal": signal_type,
        "symbol": data.get("symbol"),
    }), 200


@app.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    try:
        update = request.get_json()
        if "message" in update:
            msg     = update["message"]
            text    = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if text.startswith("/"):
                reply = handle_command(update)
                if reply:
                    send_message(reply, chat_id)
    except Exception as e:
        logger.error(f"Telegram update error: {e}")
    return jsonify({"ok": True}), 200


@app.route("/test", methods=["GET", "POST"])
def test_signal():
    try:
        data = {
            "signal"      : "LONG",
            "symbol"      : "EURUSD",
            "asset_class" : "FOREX",
            "broker"      : "IC Markets and CAPITAL.com",
            "timeframe"   : "15M",
            "entry"       : 1.08500,
            "stop_loss"   : 1.08200,
            "tp1"         : 1.09100,
            "tp2"         : 1.09700,
            "rr_tp1"      : 2.0,
            "rr_tp2"      : 4.0,
            "confidence"  : "High Confidence",
            "risk_percent": 1.0,
            "exchange"    : "OANDA",
        }
        msg     = format_signal_message(data)
        results = broadcast_message(msg)
        return jsonify({"status": "test sent", "results": results}), 200
    except Exception as e:
        logger.error(f"Test error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/test/crypto", methods=["GET", "POST"])
def test_crypto():
    try:
        data = {
            "signal"      : "LONG",
            "symbol"      : "BTCUSDT",
            "asset_class" : "CRYPTO",
            "broker"      : "Bitget",
            "crypto_type" : "FUTURES",
            "timeframe"   : "5M",
            "entry"       : 67500.00,
            "stop_loss"   : 67000.00,
            "tp1"         : 68500.00,
            "tp2"         : 69500.00,
            "rr_tp1"      : 2.0,
            "rr_tp2"      : 4.0,
            "confidence"  : "Normal",
            "risk_percent": 1.0,
            "exchange"    : "BITGET",
        }
        msg     = format_signal_message(data)
        results = broadcast_message(msg)
        return jsonify({"status": "test sent", "results": results}), 200
    except Exception as e:
        logger.error(f"Test error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/test/index", methods=["GET", "POST"])
def test_index():
    try:
        data = {
            "signal"      : "SHORT",
            "symbol"      : "NAS100",
            "asset_class" : "INDEX",
            "broker"      : "IC Markets and CAPITAL.com",
            "timeframe"   : "1H",
            "entry"       : 18500.00,
            "stop_loss"   : 18600.00,
            "tp1"         : 18300.00,
            "tp2"         : 18100.00,
            "rr_tp1"      : 2.0,
            "rr_tp2"      : 4.0,
            "confidence"  : "Highest Confidence",
            "risk_percent": 1.0,
            "exchange"    : "CAPITALCOM",
        }
        msg     = format_signal_message(data)
        results = broadcast_message(msg)
        return jsonify({"status": "test sent", "results": results}), 200
    except Exception as e:
        logger.error(f"Test error: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# TELEGRAM POLLING THREAD
# ==========================================
def telegram_polling():
    import requests as req
    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    offset = 0
    logger.info("Telegram polling started")

    while True:
        try:
            resp    = req.get(
                url,
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            updates = resp.json().get("result", [])

            for upd in updates:
                offset = upd["update_id"] + 1
                if "message" in upd:
                    msg     = upd["message"]
                    text    = msg.get("text", "")
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if text.startswith("/"):
                        reply = handle_command(upd)
                        if reply:
                            send_message(reply, chat_id)

        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)


# ==========================================
# WATCHER THREAD
# ==========================================
def run_watcher_safe():
    """Run the signal watcher safely in background."""
    try:
        from watcher import run_watcher
        run_watcher()
    except Exception as e:
        logger.error(f"Watcher error: {e}")


# ==========================================
# STARTUP
# ==========================================
def startup():
    logger.info("ICT Signal Bot Starting...")

    info = get_bot_info()
    if info.get("ok"):
        b = info["result"]
        logger.info(f"Bot: @{b.get('username')}")

    set_bot_commands()

    send_message(
        "ICT Signal Bot is ONLINE\n\n"
        "Connected and watching markets\n"
        "Signals will be sent automatically\n\n"
        "Broker Routing:\n"
        "- Forex and Indices: IC Markets and CAPITAL.com\n"
        "- Crypto: Bitget (Spot or Futures)\n\n"
        "Type /help for commands."
    )

    # Start Telegram polling thread
    polling_thread = threading.Thread(
        target=telegram_polling,
        daemon=True,
    )
    polling_thread.start()
    logger.info("Polling thread started")

    # Start signal watcher thread
    watcher_thread = threading.Thread(
        target=run_watcher_safe,
        daemon=True,
    )
    watcher_thread.start()
    logger.info("Watcher thread started")


with app.app_context():
    startup()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
