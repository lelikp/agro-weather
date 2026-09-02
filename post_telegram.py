import os
import requests
from pathlib import Path


TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = "@AgroMeteoPampa"
TXT = Path("output/alerts_latest.txt")
PROXY = os.environ.get("TELEGRAM_PROXY")

print(f"Текущая папка: {Path.cwd()}")
print(f"Файл существует: {TXT.exists()}")
print(f"Прокси: {PROXY}")

def split_messages(text, limit=4096):
    blocks = text.split("\n\n🕒")
    msgs, cur = [], ""
    for i, b in enumerate(blocks):
        piece = b if i == 0 else "\n\n🕒" + b
        if len(cur) + len(piece) > limit:
            msgs.append(cur)
            cur = piece
        else:
            cur += piece
    if cur.strip():
        msgs.append(cur)
    return msgs

def main():
    text = TXT.read_text(encoding="utf-8")
    msgs = split_messages(text)
    proxies = {"https": PROXY, "http": PROXY} if PROXY else None
    for m in msgs:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": m},
            timeout=60,
            proxies=proxies,
        )
        r.raise_for_status()
    print(f"✅ Опубликовано сообщений: {len(msgs)}")

if __name__ == "__main__":
    main()