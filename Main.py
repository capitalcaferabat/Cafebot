import re
import logging
import asyncio
from datetime import datetime
import httpx

TELEGRAM_TOKEN = "8623634734:AAGAa66_juFehSytTewhvp5c21cdWuCe6cM"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw5sCe6c3jHY-aCe19ayLH7w6nCE9mBe6d0_Ku47njRGSSq_9WO4o2p2p_TvssZAAV1yg/exec"
ALLOWED_IDS = [934460174, 5212989843]

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
TG = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
INCOME_WORDS = ["recette","مبيعات","بيع","إيراد","ايراد","دخل","كاش","مداخيل","income"]

async def tg(method, **kwargs):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{TG}/{method}", json=kwargs)
        return r.json()

async def send(chat_id, text):
    await tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")

async def save(rows):
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(APPS_SCRIPT_URL, json={"rows": rows})
            return "ok" in r.text.lower()
    except Exception as e:
        log.error("Save error: %s", e)
        return False

def extract_date(text):
    m = re.search(r'Le\s+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return datetime.now().strftime("%d/%m/%Y")

def parse(text):
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or re.match(r'(?i)^le\s+', line):
            continue
        line = re.sub(r'(?i)dh', '', line)
        line = re.sub(r',', '', line)
        line = line.strip()
        m = re.match(r'^([^\d]+?)(\d+(?:\.\d+)?)\s*$', line)
        if not m:
            m2 = re.match(r'^(\d+(?:\.\d+)?)\s+([^\d]+)$', line)
            if m2:
                amount, name = float(m2.group(1)), m2.group(2).strip()
            else:
                continue
        else:
            name, amount = m.group(1).strip(), float(m.group(2))
        if not name or amount <= 0:
            continue
        itype = "income" if any(w in name.lower() for w in INCOME_WORDS) else "expense"
        items.append({"name": name, "amount": amount, "type": itype})
    return items

async def handle(update):
    msg = update.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text = msg.get("text", "").strip()
    uname = (msg["from"].get("first_name","") + " " + msg["from"].get("last_name","")).strip()
    if not uname:
        uname = msg["from"].get("username", "مجهول")

    if ALLOWED_IDS and user_id not in ALLOWED_IDS:
        return

    if text == "/start":
        await send(chat_id,
            "☕ <b>محاسب المقهى</b>\n\n"
            "أرسل بياناتك هكذا:\n"
            "<code>Le 01/04/2026\n"
            "غاز 105dh\n"
            "الحليب 29dh\n"
            "Recette 6678dh</code>"
        )
        return

    if text == "/help":
        await send(chat_id,
            "📖 <b>طريقة الإرسال:</b>\n\n"
            "<code>Le 01/04/2026\nاسم المنتج + المبلغ\nRecette + المبلغ</code>\n\n"
            "• Recette / ايراد = إيرادات ✅\n"
            "• كل شيء آخر = مصاريف"
        )
        return

    items = parse(text)
    if not items:
        return

    date = extract_date(text)
    time_str = datetime.now().strftime("%H:%M")
    month = date[3:] if len(date) > 5 else datetime.now().strftime("%m/%Y")

    inc = sum(i["amount"] for i in items if i["type"]=="income")
    exp = sum(i["amount"] for i in items if i["type"]=="expense")
    profit = inc - exp

    rows = []
    for i in items:
        rows.append([date, time_str, uname, i["name"],
                     "إيراد" if i["type"]=="income" else "مصروف",
                     i["amount"], month])

    ok = await save(rows)

    inc_lines = "\n".join(f"  💰 {i['name']}: <b>{i['amount']:,.0f}</b>" for i in items if i["type"]=="income")
    exp_lines = "\n".join(f"  💸 {i['name']}: <b>{i['amount']:,.0f}</b>" for i in items if i["type"]=="expense")

    reply = f"📅 <b>{date}</b> — {uname}\n"
    if inc_lines:
        reply += f"\n<b>الإيرادات:</b>\n{inc_lines}\n"
    if exp_lines:
        reply += f"\n<b>المصاريف:</b>\n{exp_lines}\n"
    reply += f"\n{'─'*20}\n"
    if inc: reply += f"↑ الإيرادات: <b>{inc:,.0f}</b>\n"
    if exp: reply += f"↓ المصاريف: <b>{exp:,.0f}</b>\n"
    if inc and exp: reply += f"{'✅' if profit>=0 else '⚠️'} الربح: <b>{profit:,.0f}</b>\n"
    reply += f"\n{'✅ تم الحفظ' if ok else '❌ خطأ في الحفظ'}"

    await send(chat_id, reply)

async def main():
    log.info("☕ البوت يعمل...")
    offset = 0
    while True:
        try:
            data = await tg("getUpdates", offset=offset, timeout=30)
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                try:
                    await handle(u)
                except Exception as e:
                    log.error(e)
        except Exception as e:
            log.error(e)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
