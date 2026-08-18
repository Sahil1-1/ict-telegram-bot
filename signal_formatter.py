from datetime import datetime, timezone


def format_signal_message(data: dict) -> str:
    signal_type = data.get("signal", "UNKNOWN")

    if signal_type in ("LONG", "SHORT"):
        return _format_trade_signal(data)
    elif signal_type == "TP1_HIT":
        return _format_tp1_hit(data)
    elif signal_type == "TRADE_CLOSED":
        return _format_trade_closed(data)
    else:
        return f"📨 Alert: {data}"


def _format_trade_signal(data: dict) -> str:
    signal      = data.get("signal", "")
    symbol      = data.get("symbol", "N/A")
    asset_class = data.get("asset_class", "FOREX")
    crypto_type = data.get("crypto_type", "")
    timeframe   = data.get("timeframe", "N/A")
    entry       = data.get("entry", 0)
    stop_loss   = data.get("stop_loss", 0)
    tp1         = data.get("tp1", 0)
    tp2         = data.get("tp2", 0)
    rr_tp1      = data.get("rr_tp1", 0)
    rr_tp2      = data.get("rr_tp2", 0)
    confidence  = data.get("confidence", "Normal")
    risk_pct    = data.get("risk_percent", 1.0)
    exchange    = data.get("exchange", "")

    is_long          = signal == "LONG"
    direction_emoji  = "🟢" if is_long else "🔴"
    direction_text   = "📈 LONG  —  BUY" if is_long else "📉 SHORT  —  SELL"
    header_emoji     = "🚀" if is_long else "⬇️"

    if confidence == "Highest Confidence":
        conf_display = "⭐⭐⭐ HIGHEST CONFIDENCE"
    elif confidence == "High Confidence":
        conf_display = "🔥🔥 HIGH CONFIDENCE"
    else:
        conf_display = "✅ NORMAL"

    risk_amount    = abs(float(entry) - float(stop_loss))
    now            = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M UTC")

    # ── Broker block ──────────────────────────────────────────────────────
    if asset_class == "CRYPTO":
        crypto_line = ""
        if crypto_type == "FUTURES":
            crypto_line = "🔮 Trade Type ➜  FUTURES  (Perpetual)"
        elif crypto_type == "SPOT":
            crypto_line = "💰 Trade Type ➜  SPOT"

        broker_block = (
            "🪙  *Broker  ➜  Bitget*\n"
            f"      {crypto_line}"
        )
    else:
        broker_block = (
            "🏦  *Broker 1  ➜  IC Markets*\n"
            "🏦  *Broker 2  ➜  CAPITAL.com*\n"
            "      _(Execute on both or either)_"
        )

    msg = f"""
╔{'═' * 38}╗
║   {header_emoji}  *NEW {signal} SIGNAL*  {header_emoji}
╚{'═' * 38}╝

{direction_emoji}  *Direction*   ➜  {direction_text}
📌  *Symbol*       ➜  `{symbol}`
🏛  *Exchange*     ➜  {exchange}
📂  *Asset Class*  ➜  {asset_class}

{'─' * 40}
🏢  *BROKER DETAILS*
{'─' * 40}
{broker_block}

{'─' * 40}
⏰  *TIMEFRAME  ➜  {timeframe}*
{'─' * 40}

{'─' * 40}
📋  *TRADE LEVELS*
{'─' * 40}

▶️  *Entry Price*      ➜   `{_fp(entry)}`
🛑  *Stop Loss*        ➜   `{_fp(stop_loss)}`
🎯  *Take Profit 1*   ➜   `{_fp(tp1)}`   _← close 50% here_
🎯  *Take Profit 2*   ➜   `{_fp(tp2)}`   _← close rest here_

{'─' * 40}
📊  *RISK / REWARD*
{'─' * 40}

📏  *Risk (distance)*  ➜  `{_fp(risk_amount)}`
💰  *TP1  R:R*          ➜  `1 : {rr_tp1}`
💎  *TP2  R:R*          ➜  `1 : {rr_tp2}`
⚖️  *Risk per trade*   ➜  `{risk_pct}% of equity`

{'─' * 40}
🔍  *SIGNAL QUALITY*  ➜  {conf_display}
{'─' * 40}

{'─' * 40}
📝  *TRADE MANAGEMENT RULES*
{'─' * 40}
1️⃣  Price hits TP1  →  Close *50%* of position
2️⃣  After TP1       →  Move Stop Loss to *Breakeven*
3️⃣  Let remainder run to TP2

⏱  `{now}`

{'─' * 40}
⚠️  _This is not financial advice._
_Always manage your own risk._
{'─' * 40}
"""
    return msg.strip()


def _format_tp1_hit(data: dict) -> str:
    symbol    = data.get("symbol", "N/A")
    direction = data.get("direction", "")
    timeframe = data.get("timeframe", "N/A")
    asset     = data.get("asset_class", "")
    now       = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M UTC")

    broker_line = (
        "🪙 Bitget" if asset == "CRYPTO"
        else "🏦 IC Markets  &  CAPITAL.com"
    )

    return f"""
🎯  *TP1 HIT — PARTIAL CLOSE*  🎯

📌  Symbol     ➜  `{symbol}`
📈  Direction  ➜  {direction}
⏰  Timeframe  ➜  `{timeframe}`
{broker_line}

✅  *50% of position closed at TP1*
🔄  *Stop Loss moved to BREAKEVEN*
🏃  *Remaining 50% running toward TP2*

⏱  `{now}`
""".strip()


def _format_trade_closed(data: dict) -> str:
    symbol    = data.get("symbol", "N/A")
    direction = data.get("direction", "")
    timeframe = data.get("timeframe", "N/A")
    asset     = data.get("asset_class", "")
    now       = datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M UTC")

    broker_line = (
        "🪙 Bitget" if asset == "CRYPTO"
        else "🏦 IC Markets  &  CAPITAL.com"
    )

    return f"""
🏁  *TRADE FULLY CLOSED*  🏁

📌  Symbol     ➜  `{symbol}`
📈  Direction  ➜  {direction}
⏰  Timeframe  ➜  `{timeframe}`
{broker_line}

📊  Full position has been closed.

⏱  `{now}`
""".strip()


def _fp(price) -> str:
    """Smart price formatter."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return str(price)

    if p == 0:
        return "0"
    if p >= 1000:
        return f"{p:.2f}"
    if p >= 1:
        return f"{p:.4f}"
    if p >= 0.01:
        return f"{p:.5f}"
    return f"{p:.8f}"
