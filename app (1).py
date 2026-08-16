"""
بوت الرد التلقائي - حمام زمان
يستقبل رسايل من فيسبوك وانستجرام (ميتا) عبر webhook واحد
ويرد تلقائيًا حسب نية العميل (أسعار رجالي/حريمي، عنوان، مواعيد، حجز)
"""

import os
import re
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ============================================================
# إعدادات - كل القيم دي بتتقرأ من Environment Variables
# مبتحطش أي توكن في الكود مباشرة عشان الأمان
# ============================================================
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "hamam_zaman_verify_2026")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
GRAPH_API_URL = "https://graph.facebook.com/v21.0/me/messages"

BOOKING_PHONE = "01011115287"
MAPS_LINK = "https://goo.gl/maps/6T8M5tbUGpwzYAXq9"
MEN_PRICES_IMAGE_URL = "https://raw.githubusercontent.com/eslamemarh/hamam-zaman-bot/main/men-prices.jpg"

# ============================================================
# قاموس تخمين الجنس من الاسم الأول (أسماء عربي شائعة)
# ممكن تزود عليه أي اسم ناقص
# ============================================================
MALE_NAMES = {
    "محمد", "أحمد", "احمد", "علي", "عمر", "يوسف", "إبراهيم", "ابراهيم",
    "مصطفى", "خالد", "حسن", "حسين", "كريم", "عبدالله", "عبد الله",
    "عبدالرحمن", "عبد الرحمن", "طارق", "أسامة", "اسامة", "وليد",
    "شريف", "تامر", "هيثم", "معاذ", "سيف", "زياد", "آدم", "ادم",
    "إسلام", "اسلام", "محمود", "عمرو", "ياسر", "رامي", "أيمن", "ايمن",
    "سامح", "ماجد", "نبيل", "فادي", "جورج", "مينا", "بيشوي", "أشرف", "اشرف",
    "عصام", "سعيد", "جمال", "رضا", "فتحي", "صلاح", "ثروت", "هشام",
}

FEMALE_NAMES = {
    "فاطمة", "فاطمه", "مريم", "سارة", "ساره", "نور", "نورا", "هبة", "هبه",
    "منى", "منة", "منه", "دينا", "ياسمين", "ياسمين", "رنا", "رانيا",
    "إيمان", "ايمان", "أمل", "امل", "هدى", "سلمى", "ندى", "شيماء",
    "أميرة", "اميرة", "اميره", "أميره", "داليا", "إسراء", "اسراء",
    "روان", "جنى", "جنا", "ملك", "آية", "ايه", "اية", "هاجر", "بسمة", "بسمه",
    "مروة", "مروه", "نهى", "سحر", "وفاء", "نادين", "كريستين", "مارينا",
    "ماريان", "عبير", "رحمة", "رحمه", "زينب", "لبنى", "ريم",
}


def guess_gender(full_name: str):
    """يخمن الجنس من أول كلمة في الاسم. بيرجع 'male' / 'female' / None"""
    if not full_name:
        return None
    first_name = full_name.strip().split()[0]
    if first_name in MALE_NAMES:
        return "male"
    if first_name in FEMALE_NAMES:
        return "female"
    return None


# ============================================================
# نصوص الردود (منسوخة من ملف نص الردود المتفق عليه)
# ============================================================

WELCOME_MSG = (
    "أهلاً بيك في حمام زمان 🌿\n"
    "أقدر أساعدك في إيه؟\n\n"
    "1️⃣ أسعار الرجالي\n"
    "2️⃣ أسعار الحريمي\n"
    "3️⃣ العنوان\n"
    "4️⃣ مواعيد العمل\n"
    "5️⃣ إزاي أحجز؟"
)

MEN_PRICES_CAPTION = (
    "أسعار قسم الرجالي في حمام زمان 🧔‍♂️\n"
    f"للحجز أو أي استفسار اتصل على: {BOOKING_PHONE}"
)

WOMEN_PRICES_MSG = (
    "أسعار قسم السيدات في حمام زمان 💁‍♀️\n\n"
    "🔹 باكيدج الحمام المغربي — 775 جنيه\n"
    "🔹 باكيدج أميرات حمام زمان — 1500 جنيه\n"
    "🔹 باكيدج حمام زمان — 1500 جنيه\n"
    "🔹 باكيدج الذهب الأحمر — 2000 جنيه\n"
    "🔹 باكيدج العروسة — 2400 جنيه\n"
    "(الباكيدجات أعلاه غير شاملة سعر الليفة المغربية)\n\n"
    "🔹 مساج: 30 دقيقة = 350 جنيه | 60 دقيقة = 650 جنيه\n"
    "🔹 باديكير (إيد ورجل): بدون لون 300 جنيه | شامل لون 350 جنيه\n"
    "🔹 نتوياج (تنظيف عميق) — 400 جنيه\n"
    "🔹 فتلة للوجه — 150 جنيه\n"
    "🔹 برافين (إيد ورجل) — 200 جنيه\n"
    "🔹 سويت كامل (عدا البكيني) — 600 جنيه\n\n"
    f"للحجز أو أي استفسار اتصل على: {BOOKING_PHONE}"
)

ADDRESS_MSG = (
    "📍 عنوان حمام زمان:\n"
    "12 شارع الربيع المتفرع من شارع الطيران، أمام مستشفى التأمين الصحي، "
    "خلف سعودي ماركت، بالقرب من جنينة مول - مدينة نصر - القاهرة\n\n"
    f"الموقع على الخريطة:\n{MAPS_LINK}"
)

HOURS_MSG = (
    "⏰ مواعيد العمل:\n\n"
    "💁‍♀️ السيدات: كل أيام الأسبوع ما عدا الأحد والاثنين\n"
    "من 10 صباحًا لـ 6 مساءً (آخر استقبال 3 عصرًا)\n\n"
    "💁‍♂️ الرجال: يوميًا من 7:30 مساءً حتى 3 صباحًا (آخر استقبال 12 بالليل)\n"
    "الأحد والاثنين فقط: من 1 ظهرًا حتى 3 صباحًا (آخر استقبال 12 بالليل)"
)

BOOKING_MSG = (
    "تقدر تحجز عن طريق الاتصال بالرقم ده وهيتم تأكيد وتحديد ميعادك:\n"
    f"📞 {BOOKING_PHONE}"
)

ASK_GENDER_MSG = "حضرتك محتاج أسعار الرجالي ولا الحريمي؟ 🙏"

FALLBACK_MSG = (
    "تقدر تسأل عن: الأسعار (رجالي/حريمي) - العنوان - المواعيد - الحجز\n"
    "اختار اللي محتاجه وهرد عليك فورًا 🙏"
)

# ============================================================
# كلمات مفتاحية لكل نية
# ============================================================
KEYWORDS = {
    "men_prices": ["رجالي", "رجال", "اسعار رجال", "أسعار رجال", "حمام تركي", "حمام رجالي"],
    "women_prices": ["حريمي", "حريم", "بنات", "ستات", "سيدات", "عروسة", "عروس", "حمام حريمي"],
    "address": ["عنوان", "فين", "لوكيشن", "مكانكم", "location"],
    "hours": ["مواعيد", "إمتى", "امتى", "ساعات", "فاتحين", "فاضيين"],
    "booking": ["حجز", "أحجز", "احجز", "ازاي احجز", "عايز احجز", "عايزة احجز"],
}


def detect_intent(text: str):
    """يدور على أول نية متطابقة مع كلمات الرسالة"""
    text_normalized = text.strip().lower()
    for intent, words in KEYWORDS.items():
        for w in words:
            if w in text_normalized:
                return intent
    return None


def build_reply(message_text: str, sender_name: str = None):
    """يحدد الرد المناسب بناءً على النية + تخمين الجنس لو محتاج
    بيرجع dict: {"type": "text", "text": "..."} أو {"type": "image", "url": "...", "caption": "..."}
    """
    intent = detect_intent(message_text)

    if intent == "men_prices":
        return {"type": "image", "url": MEN_PRICES_IMAGE_URL, "caption": MEN_PRICES_CAPTION}
    if intent == "women_prices":
        return {"type": "text", "text": WOMEN_PRICES_MSG}
    if intent == "address":
        return {"type": "text", "text": ADDRESS_MSG}
    if intent == "hours":
        return {"type": "text", "text": HOURS_MSG}
    if intent == "booking":
        return {"type": "text", "text": BOOKING_MSG}

    # لو العميل كتب كلمة "أسعار" بس من غير تحديد رجالي/حريمي
    if "سعر" in message_text or "اسعار" in message_text or "أسعار" in message_text:
        gender = guess_gender(sender_name)
        if gender == "male":
            return {"type": "image", "url": MEN_PRICES_IMAGE_URL, "caption": MEN_PRICES_CAPTION}
        if gender == "female":
            return {"type": "text", "text": WOMEN_PRICES_MSG}
        return {"type": "text", "text": ASK_GENDER_MSG}

    return {"type": "text", "text": FALLBACK_MSG}


# ============================================================
# إرسال الرد عبر Graph API (شغالة لفيسبوك وانستجرام بنفس الفورمات)
# ============================================================
def send_message(recipient_id: str, text: str):
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    resp = requests.post(GRAPH_API_URL, params=params, json=payload, timeout=10)
    if resp.status_code != 200:
        app.logger.error("فشل إرسال الرسالة: %s", resp.text)
    return resp


def send_image(recipient_id: str, image_url: str, caption: str = None):
    """يبعت صورة (ولو فيه كابشن، يبعته كرسالة نص منفصلة بعد الصورة)"""
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url, "is_reusable": True},
            }
        },
    }
    params = {"access_token": PAGE_ACCESS_TOKEN}
    resp = requests.post(GRAPH_API_URL, params=params, json=payload, timeout=15)
    if resp.status_code != 200:
        app.logger.error("فشل إرسال الصورة: %s", resp.text)
    if caption:
        send_message(recipient_id, caption)
    return resp


def get_user_name(sender_id: str):
    """يجيب اسم صاحب الأكونت من الـ Graph API (لو الصلاحية متاحة)"""
    try:
        url = f"https://graph.facebook.com/{sender_id}"
        params = {"fields": "first_name,last_name", "access_token": PAGE_ACCESS_TOKEN}
        resp = requests.get(url, params=params, timeout=5)
        data = resp.json()
        first = data.get("first_name", "")
        last = data.get("last_name", "")
        return f"{first} {last}".strip()
    except Exception as e:
        app.logger.warning("مقدرتش أجيب اسم المستخدم: %s", e)
        return None


# ============================================================
# مسارات الـ Webhook
# ============================================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """ميتا بتستخدم ده مرة واحدة بس وقت ربط الـ webhook"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.get_json(force=True, silent=True) or {}

    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            sender_id = event.get("sender", {}).get("id")
            message = event.get("message", {})
            text = message.get("text")

            if not sender_id or not text:
                continue

            sender_name = get_user_name(sender_id)
            reply = build_reply(text, sender_name)
            if reply["type"] == "image":
                send_image(sender_id, reply["url"], reply.get("caption"))
            else:
                send_message(sender_id, reply["text"])

    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def health_check():
    return "حمام زمان بوت شغال ✅", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
