"""
بوت الرد التلقائي - حمام زمان
يستقبل رسايل من فيسبوك وانستجرام (ميتا) عبر webhook واحد
ويرد تلقائيًا حسب نية العميل (أسعار رجالي/حريمي، عنوان، مواعيد، حجز)

كل النصوص والأسعار والأرقام موجودة في content.py — عدّل هناك بس.
الملف ده فيه المنطق البرمجي، نادرًا ما هتحتاج تلمسه.
"""

import os
import requests
from flask import Flask, request, jsonify

import content

app = Flask(__name__)

# ============================================================
# إعدادات - كل القيم دي بتتقرأ من Environment Variables
# مبتحطش أي توكن في الكود مباشرة عشان الأمان
# ============================================================
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "hamam_zaman_verify_2026")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "")
GRAPH_API_URL = "https://graph.facebook.com/v21.0/me/messages"


def guess_gender(full_name: str):
    """يخمن الجنس من أول كلمة في الاسم. بيرجع 'male' / 'female' / None"""
    if not full_name:
        return None
    first_name = full_name.strip().split()[0]
    if first_name in content.MALE_NAMES:
        return "male"
    if first_name in content.FEMALE_NAMES:
        return "female"
    return None


def detect_intent(text: str):
    """يدور على أول نية متطابقة مع كلمات الرسالة"""
    text_normalized = text.strip().lower()
    for intent, words in content.KEYWORDS.items():
        for w in words:
            if w in text_normalized:
                return intent
    return None


# كل نية (غير men_prices) بترجعلها نص واحد ثابت من content.py
TEXT_REPLIES = {
    "women_prices": content.WOMEN_PRICES_MSG,
    "address": content.ADDRESS_MSG,
    "hours": content.HOURS_MSG,
    "booking": content.BOOKING_MSG,
    "pkg_aroosa": content.WOMEN_AROOSA_MSG,
    "pkg_amirat": content.WOMEN_AMIRAT_MSG,
    "pkg_zahab": content.WOMEN_ZAHAB_MSG,
    "pkg_hamam_zaman_w": content.WOMEN_HAMAM_ZAMAN_MSG,
    "pkg_maghrebi": content.WOMEN_MAGHREBI_MSG,
    "pkg_massage": content.WOMEN_MASSAGE_MSG,
    "pkg_pedicure": content.WOMEN_PEDICURE_MSG,
    "pkg_netwaya": content.WOMEN_NETWAYA_MSG,
    "pkg_fatla": content.WOMEN_FATLA_MSG,
    "pkg_brafin": content.WOMEN_BRAFIN_MSG,
    "pkg_sweat": content.WOMEN_SWEAT_MSG,
}


def build_reply(message_text: str, sender_name: str = None):
    """يحدد الرد المناسب بناءً على النية + تخمين الجنس لو محتاج
    بيرجع dict: {"type": "text", "text": "..."} أو {"type": "image", "url": "...", "caption": "..."}
    """
    intent = detect_intent(message_text)

    if intent == "men_prices":
        return {"type": "image", "url": content.MEN_PRICES_IMAGE_URL, "caption": content.MEN_PRICES_CAPTION}

    if intent in TEXT_REPLIES:
        return {"type": "text", "text": TEXT_REPLIES[intent]}

    # لو العميل كتب كلمة "أسعار" بس من غير تحديد رجالي/حريمي
    if "سعر" in message_text or "اسعار" in message_text or "أسعار" in message_text:
        gender = guess_gender(sender_name)
        if gender == "male":
            return {"type": "image", "url": content.MEN_PRICES_IMAGE_URL, "caption": content.MEN_PRICES_CAPTION}
        if gender == "female":
            return {"type": "text", "text": content.WOMEN_PRICES_MSG}
        return {"type": "text", "text": content.ASK_GENDER_MSG}

    return {"type": "text", "text": content.FALLBACK_MSG}


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
