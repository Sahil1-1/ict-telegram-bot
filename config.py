import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET     = os.getenv("WEBHOOK_SECRET", "default_secret")
ADMIN_USER_IDS     = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
    if uid.strip().isdigit()
]
PORT         = int(os.getenv("PORT", 5000))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///signals.db")
