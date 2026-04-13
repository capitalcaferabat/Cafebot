 import re
import logging
import asyncio
from datetime import datetime
import httpx

# --- الإعدادات ---
TELEGRAM_TOKEN = "8623634734:AAH4SvIMsKnVsWQK6fE-vebQMscCgJa3ca4"
# الرابط الجديد الذي أرسلته
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbykNDwSsFosnGgQn00Ef_j6gVpV_1zzO2ohSz7rBYUJjW2aVvY9DqveF5Xv1gqKZ7oOKg/exec"
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
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return {"ok": False}

async def send(chat_id, text):
    await tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")

async def save(rows):
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.post(APPS_SCRIPT_URL, json={"rows": rows})
            return "ok" in r.text.lower()
    except Exception as e:
        log.error(f"Save error: {e}")
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
        
        if not name or amount <= 0: continue
        itype = "income" if any(w in name.lower() for w in INCOME_WORDS) else "expense"
        items.append({"name": name, "amount": amount, "type": itype})
    return items

async def handle(update):
    msg = update.get("message")
    if not msg or "text" not in msg: return
    chat_id, user_id, text = msg["chat"]["id"], msg["from"]["id"], msg["text"].strip()
    uname = (msg["from"].get("first_name", "") + " " + msg["from"].get("last_name", "")).strip() or "User"
    
    if ALLOWED_IDS and user_id not in ALLOWED_IDS: return

    if text == "/start":
        await send(chat_id, "☕ <b>محاسب المقهى</b>\nأرسل البيانات وسأقوم بحفظها.")
        return

    items = parse(text)
    if not items: return
    
    date = extract_date(text)
    time_str = datetime.now().strftime("%H:%M")
    
    # تنسيق الشهر للعمود G
    d_parts = date.split('/')
    month = f"{d_parts[1]}/{d_parts[2]}" if len(d_parts) == 3 else datetime.now().strftime("%m/%Y")

    rows = [[date, time_str, uname, i["name"], "إيراد" if i["type"]=="income" else "مصروف", i["amount"], month] for i in items]
    
    ok = await save(rows)
    
    # الحسابات للرسالة
    inc_total = sum(i["amount"] for i in items if i["type"] == "income")
    exp_total = sum(i["amount"] for i in items if i["type"] == "expense")
    profit = inc_total - exp_total

    # بناء الرسالة
    reply = f"📅 <b>{date}</b> — {uname}\n"
    reply += "────────────────────\n"
    for i in items:
        icon = "💰" if i["type"] == "income" else "💸"
        reply += f"{icon} {i['name']}: <b>{i['amount']:,.0f} DH</b>\n"
    
    reply += "────────────────────\n"
    if inc_total: reply += f"إجمالي الإيرادات: <b>{inc_total:,.0f} DH</b>\n"
    reply += f"إجمالي المصاريف: <b>{exp_total:,.0f} DH</b>\n"
    reply += f"صافي اليوم: <b>{profit:,.0f} DH</b>\n"
    reply += f"\n{'✅ تم الحفظ بنجاح' if ok else '❌ خطأ في الحفظ'}"

    await send(chat_id, reply)

async def main():
    log.info("🚀 البوت يعمل بالنسخة المستقرة...")
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
        except Exception: await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
