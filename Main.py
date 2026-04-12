import re
import logging
import asyncio
from datetime import datetime
import httpx

# --- الإعدادات النهائية ---
TELEGRAM_TOKEN = "8623634734:AAH4SvIMsKnVsWQK6fE-vebQMscCgJa3ca4"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxpUAkSWNv94E0Woow6omGHi8MeUP4cGw_uLhLPuD9y44DpvKDqRx-xmpszsFkRO52eSg/exec"
ALLOWED_IDS = [934460174, 5212989843]

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
TG = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
INCOME_WORDS = ["recette", "مبيعات", "بيع", "إيراد", "ايراد", "دخل", "كاش", "مداخيل", "income"]

async def tg(method, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{TG}/{method}", json=kwargs)
            return r.json()
    except Exception: return {"ok": False}

async def send(chat_id, text):
    await tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")

async def save(rows):
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.post(APPS_SCRIPT_URL, json={"rows": rows})
            return "ok" in r.text.lower()
    except Exception as e:
        log.error(f"Error: {e}")
        return False

def extract_date(text):
    m = re.search(r'Le\s+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', text, re.IGNORECASE)
    if m: return m.group(1)
    return datetime.now().strftime("%d/%m/%Y")

def parse(text):
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or re.match(r'(?i)^le\s+', line): continue
        line = re.sub(r'(?i)dh', '', line).replace(',', '').strip()
        m = re.match(r'^([^\d]+?)(\d+(?:\.\d+)?)\s*$', line)
        if not m:
            m2 = re.match(r'^(\d+(?:\.\d+)?)\s+([^\d]+)$', line)
            if m2: amount, name = float(m2.group(1)), m2.group(2).strip()
            else: continue
        else: name, amount = m.group(1).strip(), float(m.group(2))
        itype = "income" if any(w in name.lower() for w in INCOME_WORDS) else "expense"
        items.append({"name": name, "amount": amount, "type": itype})
    return items

async def handle(update):
    msg = update.get("message")
    if not msg or "text" not in msg: return
    chat_id, user_id, text = msg["chat"]["id"], msg["from"]["id"], msg["text"].strip()
    uname = (msg["from"].get("first_name", "") + " " + msg["from"].get("last_name", "")).strip() or "مجهول"
    if ALLOWED_IDS and user_id not in ALLOWED_IDS: return

    items = parse(text)
    if not items: return
    date = extract_date(text); time_str = datetime.now().strftime("%H:%M")
    month = date[3:] if len(date) > 5 else datetime.now().strftime("%m/%Y")

    rows = [[date, time_str, uname, i["name"], "إيراد" if i["type"]=="income" else "مصروف", i["amount"], month] for i in items]
    ok = await save(rows)

    inc_total = sum(i["amount"] for i in items if i["type"]=="income")
    exp_total = sum(i["amount"] for i in items if i["type"]=="expense")

    reply = f"📅 <b>{date}</b> — {uname}\n"
    reply += f"\n{'✅ تم الحفظ في الشيت' if ok else '❌ فشل في الوصول للشيت'}\n"
    reply += "────────────────────\n"
    for i in items:
        icon = "💰" if i["type"] == "income" else "💸"
        reply += f"{icon} {i['name']}: <b>{i['amount']:,} DH</b>\n"
    reply += "────────────────────\n"
    reply += f"صافي اليوم: <b>{inc_total - exp_total:,} DH</b>"
    await send(chat_id, reply)

async def main():
    log.info("🚀 Active...")
    await tg("deleteWebhook", drop_pending_updates=True)
    offset = 0
    while True:
        try:
            data = await tg("getUpdates", offset=offset, timeout=30)
            if data.get("ok"):
                for u in data.get("result", []):
                    offset = u["update_id"] + 1
                    asyncio.create_task(handle(u))
            else: await asyncio.sleep(5)
        except: await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
