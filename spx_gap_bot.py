#!/usr/bin/env python3
“””
SPX Options Gap Scanner — Telegram Bot
يراقب فجوات الأسعار على عقود SPX Options ويرسل تنبيهات تلجرام
“””

import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

# ─── إعدادات البوت ───────────────────────────────────────────

TELEGRAM_TOKEN = “8246852369:AAGqdhOS2G_pXaONn4Bqesy4pgjGuNsiJ3Q”
CHAT_ID        = “5750592750”
CHECK_INTERVAL = 60   # كل كم ثانية يفحص (60 = دقيقة)
GAP_THRESHOLD  = 0.20 # نسبة الفجوة المطلوبة (20%)
ET = pytz.timezone(“America/New_York”)

# ─── إرسال رسالة تلجرام ──────────────────────────────────────

def send_telegram(msg: str):
url = f”https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage”
payload = {
“chat_id”: CHAT_ID,
“text”: msg,
“parse_mode”: “HTML”
}
try:
r = requests.post(url, json=payload, timeout=10)
r.raise_for_status()
print(f”✅ تم الإرسال: {datetime.now(ET).strftime(’%H:%M:%S’)}”)
except Exception as e:
print(f”❌ خطأ في الإرسال: {e}”)

# ─── جلب بيانات SPX ──────────────────────────────────────────

def get_spx_price():
try:
ticker = yf.Ticker(”^GSPC”)
data = ticker.history(period=“1d”, interval=“1m”)
if data.empty:
return None
latest = data.iloc[-1]
return {
“price”: round(latest[“Close”], 2),
“high”:  round(latest[“High”], 2),
“low”:   round(latest[“Low”], 2),
“volume”: int(latest[“Volume”]),
“time”:  data.index[-1].tz_convert(ET).strftime(”%H:%M”)
}
except Exception as e:
print(f”❌ خطأ في جلب SPX: {e}”)
return None

# ─── جلب بيانات Options ──────────────────────────────────────

def get_options_data(symbol=”^GSPC”):
try:
ticker = yf.Ticker(symbol)
expirations = ticker.options

```
    # أقرب انتهاء (هذا الأسبوع أو القادم)
    today = datetime.now(ET).date()
    upcoming = [e for e in expirations
                if datetime.strptime(e, "%Y-%m-%d").date() >= today]
    if not upcoming:
        return None, None

    exp = upcoming[0]
    chain = ticker.option_chain(exp)
    return chain.puts, exp
except Exception as e:
    print(f"❌ خطأ في جلب Options: {e}")
    return None, None
```

# ─── كشف الفجوات ─────────────────────────────────────────────

def detect_gaps(df: pd.DataFrame):
“””
يكشف الفجوات السعرية في عقود الـ Options
الفجوة = فرق كبير بين Bid و Ask أو بين أسعار متتالية
“””
gaps = []
if df is None or df.empty:
return gaps

```
# فرز حسب الـ Strike
df = df.sort_values("strike").reset_index(drop=True)

for i in range(1, len(df)):
    prev = df.iloc[i-1]
    curr = df.iloc[i]

    # تجاهل العقود بدون سعر
    if prev["lastPrice"] <= 0 or curr["lastPrice"] <= 0:
        continue

    # حساب نسبة الفجوة بين سعرين متتاليين
    gap_pct = abs(curr["lastPrice"] - prev["lastPrice"]) / prev["lastPrice"]

    if gap_pct >= GAP_THRESHOLD:
        gaps.append({
            "strike_low":  prev["strike"],
            "strike_high": curr["strike"],
            "price_low":   round(prev["lastPrice"], 2),
            "price_high":  round(curr["lastPrice"], 2),
            "gap_pct":     round(gap_pct * 100, 1),
            "bid":         curr["bid"],
            "ask":         curr["ask"],
            "volume":      curr.get("volume", 0),
            "openInterest": curr.get("openInterest", 0)
        })

return gaps
```

# ─── حساب Stop و Target ──────────────────────────────────────

def calculate_levels(entry_price: float, gap_low: float):
stop   = round(gap_low * 0.85, 2)          # 15% تحت قاع الفجوة
t1     = round(entry_price * 2.0, 2)        # Target 1 = 2x
t2     = round(entry_price * 3.5, 2)        # Target 2 = 3.5x
t3     = round(entry_price * 6.0, 2)        # Target 3 = 6x (Gamma explosion)
risk   = round(entry_price - stop, 2)
rr1    = round((t1 - entry_price) / risk, 1) if risk > 0 else 0
return stop, t1, t2, t3, rr1

# ─── بناء رسالة التنبيه ──────────────────────────────────────

def build_alert(gap: dict, spx: dict, expiration: str) -> str:
entry  = round((gap[“price_low”] + gap[“price_high”]) / 2, 2)
stop, t1, t2, t3, rr = calculate_levels(entry, gap[“price_low”])

```
now = datetime.now(ET).strftime("%Y-%m-%d %H:%M")

msg = f"""
```

🚨 <b>تنبيه فجوة — SPX Options</b>

📅 <b>التاريخ:</b> {now} ET
📆 <b>انتهاء العقد:</b> {expiration}

📊 <b>SPX الحالي:</b> {spx[‘price’]} نقطة
🕐 <b>آخر تحديث:</b> {spx[‘time’]}

─────────────────────
⚡ <b>تفاصيل الفجوة</b>

Strike المنخفض:  {gap[‘strike_low’]}  →  سعر العقد: <b>${gap[‘price_low’]}</b>
Strike المرتفع:  {gap[‘strike_high’]} →  سعر العقد: <b>${gap[‘price_high’]}</b>
حجم الفجوة: <b>{gap[‘gap_pct’]}%</b>
Volume: {gap[‘volume’]:,}  |  OI: {gap[‘openInterest’]:,}

─────────────────────
🎯 <b>خطة التداول</b>

نقطة الدخول:  <b>${entry}</b>
🛑 Stop Loss:  <b>${stop}</b>
✅ Target 1:   <b>${t1}</b>  (2x)
✅ Target 2:   <b>${t2}</b>  (3.5x)
🚀 Target 3:   <b>${t3}</b>  (6x — Gamma)

نسبة Risk/Reward: <b>1:{rr}</b>

─────────────────────
💡 <b>الاستراتيجية</b>

• الفجوة بين ${gap[‘price_low’]} و ${gap[‘price_high’]} = مستوى دعم قوي
• إذا العقد رجع لاختبار الفجوة = فرصة دخول
• انتظر تأكيد الارتداد قبل الدخول
• لا تخاطر بأكثر من 1-2% من رأس المال

⚠️ هذا تحليل تقني فقط — ليس توصية استثمارية
“””
return msg.strip()

# ─── فحص وقت التداول ─────────────────────────────────────────

def is_market_open():
now = datetime.now(ET)
# السوق مفتوح الإثنين-الجمعة 9:30 - 16:00
if now.weekday() >= 5:  # السبت والأحد
return False
market_open  = now.replace(hour=9,  minute=30, second=0)
market_close = now.replace(hour=16, minute=0,  second=0)
return market_open <= now <= market_close

# ─── الحلقة الرئيسية ─────────────────────────────────────────

def main():
print(“🤖 بوت SPX Gap Scanner يعمل…”)
send_telegram(“🤖 <b>بوت SPX Gap Scanner</b> بدأ العمل!\n\nسيراقب فجوات Options ويرسل تنبيهات فورية 📊”)

```
last_gaps = set()  # لتجنب إرسال نفس التنبيه مرتين

while True:
    try:
        if not is_market_open():
            now = datetime.now(ET)
            print(f"💤 السوق مغلق — {now.strftime('%A %H:%M')}")
            time.sleep(300)  # انتظر 5 دقائق
            continue

        print(f"🔍 فحص الفجوات... {datetime.now(ET).strftime('%H:%M:%S')}")

        # جلب البيانات
        spx = get_spx_price()
        puts, expiration = get_options_data()

        if spx is None or puts is None:
            print("⚠️ تعذر جلب البيانات")
            time.sleep(CHECK_INTERVAL)
            continue

        # كشف الفجوات
        gaps = detect_gaps(puts)

        if gaps:
            print(f"✅ وجدت {len(gaps)} فجوة")
            for gap in gaps:
                # مفتاح فريد لكل فجوة
                gap_key = f"{gap['strike_low']}-{gap['strike_high']}-{expiration}"

                if gap_key not in last_gaps:
                    msg = build_alert(gap, spx, expiration)
                    send_telegram(msg)
                    last_gaps.add(gap_key)
                    time.sleep(2)  # تأخير بين الرسائل
        else:
            print("لا توجد فجوات حالياً")

        # تنظيف الفجوات القديمة كل ساعة
        if len(last_gaps) > 50:
            last_gaps.clear()

        time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n⛔ تم إيقاف البوت")
        send_telegram("⛔ تم إيقاف بوت SPX Gap Scanner")
        break
    except Exception as e:
        print(f"❌ خطأ: {e}")
        time.sleep(CHECK_INTERVAL)
```

if **name** == “**main**”:
main()
