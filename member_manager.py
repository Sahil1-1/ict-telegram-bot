import logging
from database import (
    add_member, add_chat_group, remove_chat_group,
    get_recent_signals, SessionLocal, Signal
)
from signal_formatter import format_signal_message, _fp
from config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)


def handle_command(update: dict) -> str:
    msg        = update.get("message", {})
    text       = msg.get("text", "").strip()
    chat_id    = str(msg.get("chat", {}).get("id", ""))
    chat_type  = msg.get("chat", {}).get("type", "private")
    chat_title = msg.get("chat", {}).get("title", "Private Chat")
    user       = msg.get("from", {})
    user_id    = user.get("id", 0)
    username   = user.get("username", "")
    first_name = user.get("first_name", "")

    # Parse command (strip @botname if present)
    parts   = text.split()
    command = parts[0].lower().split("@")[0] if parts else ""

    if command == "/start":
        return _start(chat_id, user_id, username, first_name, chat_type)
    elif command == "/help":
        return _help()
    elif command == "/status":
        return _status()
    elif command == "/lastsignal":
        return _last_signal()
    elif command == "/stats":
        return _stats()
    elif command == "/addgroup":
        return _add_group(chat_id, chat_title, user_id, chat_type)
    elif command == "/removegroup":
        return _remove_group(chat_id, user_id, chat_type)

    return ""


def _start(chat_id, user_id, username, first_name, chat_type):
    add_member(user_id, username, first_name)
    if chat_type in ("group", "supergroup"):
        add_chat_group(chat_id, "")

    return f"""
👋 *Welcome {first_name}!*

You're now registered with the *ICT Institutional Signal Bot*.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 *What you'll receive:*
• Live ICT strategy signals
• Entry, Stop Loss, TP1 & TP2
• Exact broker to use
• Timeframe for each trade
• Crypto: SPOT vs FUTURES label
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏢 *Broker Routing:*
• Forex & Indices → IC Markets & CAPITAL.com
• Crypto         → Bitget
━━━━━━━━━━━━━━━━━━━━━━━━━━━

Type /help to see all commands.
""".strip()


def _help():
    return """
📖 *ICT Signal Bot — Commands*

/start        → Register yourself
/help         → This message
/status       → Check bot is online
/lastsignal   → View last signal
/stats        → Signal statistics

*Admin only:*
/addgroup     → Register this group
/removegroup  → Remove this group

━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Every signal includes:*
✅ Direction  (LONG / SHORT)
✅ Broker name
✅ Timeframe
✅ Entry price
✅ Stop Loss
✅ TP1  &  TP2
✅ Risk : Reward
✅ Confidence level
✅ Crypto: Spot vs Futures
━━━━━━━━━━━━━━━━━━━━━━━━━━━
*Trade Rules:*
• TP1 hit → Close 50%, move SL to breakeven
• TP2 hit → Close remaining position
""".strip()


def _status():
    session = SessionLocal()
    try:
        total = session.query(Signal).count()
    finally:
        session.close()

    return f"""
🟢 *Bot Status: ONLINE*

📊 Total signals processed: `{total}`
⏰ Listening for TradingView webhooks

🏢 *Active Broker Routing:*
• Forex / Indices → IC Markets & CAPITAL.com
• Crypto         → Bitget (Spot / Futures)
""".strip()


def _last_signal():
    signals = get_recent_signals(1)
    if not signals:
        return "📭 No signals received yet. Waiting for TradingView..."

    s    = signals[0]
    data = {
        "signal"      : s.signal_type,
        "symbol"      : s.symbol,
        "asset_class" : s.asset_class,
        "broker"      : s.broker,
        "crypto_type" : s.crypto_type or "",
        "timeframe"   : s.timeframe,
        "entry"       : s.entry,
        "stop_loss"   : s.stop_loss,
        "tp1"         : s.tp1,
        "tp2"         : s.tp2,
        "rr_tp1"      : s.rr_tp1 or 0,
        "rr_tp2"      : s.rr_tp2 or 0,
        "confidence"  : s.confidence,
        "risk_percent": s.risk_percent,
        "exchange"    : s.exchange,
    }

    if s.signal_type in ("LONG", "SHORT"):
        return format_signal_message(data)

    return (
        f"📌 *Last Signal:* {s.signal_type}\n"
        f"Symbol: `{s.symbol}`\n"
        f"Time: `{s.timestamp}`"
    )


def _stats():
    session = SessionLocal()
    try:
        total   = session.query(Signal).count()
        longs   = session.query(Signal).filter_by(signal_type="LONG").count()
        shorts  = session.query(Signal).filter_by(signal_type="SHORT").count()
        tp1h    = session.query(Signal).filter_by(signal_type="TP1_HIT").count()
        closed  = session.query(Signal).filter_by(signal_type="TRADE_CLOSED").count()
        forex   = session.query(Signal).filter_by(asset_class="FOREX").count()
        indices = session.query(Signal).filter_by(asset_class="INDEX").count()
        crypto  = session.query(Signal).filter_by(asset_class="CRYPTO").count()
    finally:
        session.close()

    total_trades = longs + shorts
    wr = (tp1h / total_trades * 100) if total_trades > 0 else 0

    return f"""
📊 *Signal Statistics*

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈  Long signals    ➜  `{longs}`
📉  Short signals   ➜  `{shorts}`
🎯  TP1 hits        ➜  `{tp1h}`
🏁  Trades closed   ➜  `{closed}`
📉  Est. win rate   ➜  `{wr:.1f}%`
━━━━━━━━━━━━━━━━━━━━━━━━━━━
💱  Forex signals   ➜  `{forex}`
📊  Index signals   ➜  `{indices}`
🪙  Crypto signals  ➜  `{crypto}`
━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()


def _add_group(chat_id, chat_title, user_id, chat_type):
    if user_id not in ADMIN_USER_IDS:
        return "⛔ Admin only command."
    if chat_type not in ("group", "supergroup"):
        return "ℹ️ Run this command inside a group."
    add_chat_group(chat_id, chat_title)
    return f"✅ *{chat_title}* registered!\nChat ID: `{chat_id}`"


def _remove_group(chat_id, user_id, chat_type):
    if user_id not in ADMIN_USER_IDS:
        return "⛔ Admin only command."
    remove_chat_group(chat_id)
    return "✅ Group removed from signal broadcasts."
