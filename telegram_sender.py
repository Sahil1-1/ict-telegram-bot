import requests
import logging
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database import get_active_chat_ids

logger = logging.getLogger(__name__)

API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_message(text: str, chat_id: str = None) -> bool:
    target = str(chat_id or TELEGRAM_CHAT_ID)
    url    = f"{API}/sendMessage"
    payload = {
        "chat_id"                  : target,
        "text"                     : text,
        "parse_mode"               : "Markdown",
        "disable_web_page_preview" : True,
    }
    try:
        r      = requests.post(url, json=payload, timeout=30)
        result = r.json()
        if result.get("ok"):
            logger.info(f"✅ Message sent to {target}")
            return True
        else:
            desc = result.get("description", "")
            logger.error(f"❌ Telegram error for {target}: {desc}")
            # Retry as plain text if Markdown fails
            if "parse" in desc.lower():
                return _send_plain(text, target)
            return False
    except requests.RequestException as e:
        logger.error(f"Network error: {e}")
        return False


def _send_plain(text: str, chat_id: str) -> bool:
    clean = (
        text.replace("*", "")
            .replace("_", "")
            .replace("`", "")
            .replace("[", "")
            .replace("]", "")
    )
    url = f"{API}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": chat_id, "text": clean},
            timeout=30,
        )
        return r.json().get("ok", False)
    except requests.RequestException:
        return False


def broadcast_message(text: str) -> dict:
    results = {}

    # Always send to primary group
    results[TELEGRAM_CHAT_ID] = send_message(text, TELEGRAM_CHAT_ID)

    # Send to any additional registered groups
    for cid in get_active_chat_ids():
        if cid != str(TELEGRAM_CHAT_ID):
            results[cid] = send_message(text, cid)

    return results


def get_bot_info() -> dict:
    try:
        return requests.get(f"{API}/getMe", timeout=10).json()
    except Exception:
        return {}


def set_bot_commands():
    commands = [
        {"command": "start",       "description": "Register and start"},
        {"command": "help",        "description": "Show all commands"},
        {"command": "status",      "description": "Bot status"},
        {"command": "lastsignal",  "description": "Last trading signal"},
        {"command": "stats",       "description": "Signal statistics"},
        {"command": "addgroup",    "description": "Register group (Admin)"},
        {"command": "removegroup", "description": "Remove group (Admin)"},
    ]
    try:
        requests.post(
            f"{API}/setMyCommands",
            json={"commands": commands},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Error setting commands: {e}")
