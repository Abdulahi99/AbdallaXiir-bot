import os
import time
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types
from google.genai.errors import APIError

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = (
    "Waxaad tahay AbdallaXIIR, kaaliye shaqsi ah oo caawiya hawl-maalmeedka "
    "qorsheynta maalinlaha ah, xusuusinta hawsha, tarjumaadda, barashada, "
    "iyo su'aalaha guud. "
    "Mar walba ku jawaab luqadda uu qofku wax ku weydiiyay: haddii fariintu "
    "Af-Soomaali tahay ku jawaab Af-Soomaali cad oo asluub leh; haddii fariintu "
    "Af-Ingiriisi tahay ku jawaab Af-Ingiriisi cad oo dabiici ah. "
    "Jawaabahaaga ka dhig kuwo nadiif ah, kooban oo waxtar leh."
)

MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


def send_telegram_message(chat_id: int, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        part = text[i:i + chunk_size]
        try:
            requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": part,
                },
                timeout=20,
            )
        except requests.RequestException:
            pass


def ask_ai_with_retry(user_text: str) -> str:
    for model_name in MODELS_TO_TRY:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.7,
                    ),
                )
                if response and response.text:
                    return response.text.strip()
            except APIError as e:
                status_code = getattr(e, "code", None)
                if status_code in (503, 429) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                break
            except Exception:
                break
    return (
        "Waan ka xunahay, AI-ga ayaa hadda culeys ku jira ama cilad ku meel gaar ah "
        "ayaa dhacday. Fadlan daqiiqad yar sug ka dibna mar kale isku day.\n\n"
        "Sorry, the AI service is currently busy or temporarily unavailable. "
        "Please wait a moment and try again."
    )


@app.route("/", methods=["GET"])
def home():
    return "AbdallaXIIR bot server is running.", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    message = data.get("message") or data.get("edited_message")
    if not message:
        return jsonify({"ok": True}), 200

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")

    if not chat_id:
        return jsonify({"ok": True}), 200

    if not text:
        send_telegram_message(
            chat_id,
            "Fadlan ii soo dir fariin qoraal ah (Af-Soomaali ama Af-Ingiriisi) si aan kuugu caawiyo.\n"
            "Please send a text message (in Somali or English) so I can help you."
        )
        return jsonify({"ok": True}), 200

    if text.strip() == "/start":
        send_telegram_message(
            chat_id,
            "Ku soo dhawoow AbdallaXIIR! Waxaan kaa caawin karaa hawlahaaga maalinlaha ah "
            "(qorsheyn, tarjumaad, barasho, iyo su'aalo guud) Af-Soomaali iyo Af-Ingiriisi.\n\n"
            "Welcome to AbdallaXIIR! I can help with your daily tasks, planning, "
            "translation, learning, and general questions in Somali and English."
        )
        return jsonify({"ok": True}), 200

    reply = ask_ai_with_retry(text)
    send_telegram_message(chat_id, reply)
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)