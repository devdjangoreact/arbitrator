"""Send a test Telegram message using credentials from .env."""
from __future__ import annotations

import urllib.request
import urllib.parse
import json
import sys
from pathlib import Path

env = Path(__file__).resolve().parent.parent / ".env"
token = chat_id = ""
for line in env.read_text(encoding="utf-8").splitlines():
    if line.startswith("TELEGRAM_BOT_TOKEN="):
        token = line.split("=", 1)[1].strip()
    elif line.startswith("TELEGRAM_CHAT_ID="):
        chat_id = line.split("=", 1)[1].strip()

if not token:
    sys.exit("❌ TELEGRAM_BOT_TOKEN порожній в .env")
if not chat_id:
    sys.exit("❌ TELEGRAM_CHAT_ID порожній в .env  →  запусти scripts/get_telegram_chat_id.py")

payload = json.dumps({
    "chat_id": chat_id,
    "text": "✅ <b>Arbitrator test</b>\nТелеграм сповіщення працює!",
    "parse_mode": "HTML",
}).encode()

req = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/sendMessage",
    data=payload,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.loads(r.read())

if data.get("ok"):
    print("✅ Повідомлення відправлено!")
else:
    print(f"❌ Помилка: {data}")
