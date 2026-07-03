"""Run once to find your Telegram chat_id. Then set TELEGRAM_CHAT_ID in .env."""
from __future__ import annotations

import urllib.request
import json
import sys
from pathlib import Path

# read token from .env
token = ""
env = Path(__file__).resolve().parent.parent / ".env"
for line in env.read_text(encoding="utf-8").splitlines():
    if line.startswith("TELEGRAM_BOT_TOKEN="):
        token = line.split("=", 1)[1].strip()
        break

if not token:
    sys.exit("TELEGRAM_BOT_TOKEN not found in .env")

url = f"https://api.telegram.org/bot{token}/getUpdates"
with urllib.request.urlopen(url, timeout=10) as r:
    data = json.loads(r.read())

if not data.get("ok"):
    sys.exit(f"API error: {data}")

results = data.get("result", [])
if not results:
    print("No updates yet.")
    print("→ Відправ будь-яке повідомлення боту (або в групу де він є) і запусти скрипт знову.")
    sys.exit(0)

seen: set[str] = set()
for upd in results:
    msg = upd.get("message") or upd.get("channel_post") or {}
    chat = msg.get("chat", {})
    cid = str(chat.get("id", ""))
    if cid and cid not in seen:
        seen.add(cid)
        title = chat.get("title") or chat.get("username") or chat.get("first_name", "")
        kind = chat.get("type", "")
        print(f"chat_id={cid}  type={kind}  name={title}")

print("\n→ Скопіюй потрібний chat_id в .env: TELEGRAM_CHAT_ID=<id>")
