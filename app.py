import os
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

TELEGRAM_TOKEN = (
    os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or ""
).strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
TRADE_EXECUTION_ENABLED = (
    os.environ.get("TRADE_EXECUTION_ENABLED") or "false"
).strip().lower() == "true"

_client = None
_working_model = None


def get_gemini_client():
    global _client
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable")
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


SYSTEM_INSTRUCTION = """
Waxaad tahay caawiye AI ah oo degdeg ah, cad, oo nidaamsan una shaqeeya @AbdallaXiir_bot.
Had iyo jeer ku jawaab Af-Soomaali cad oo fudud in la akhriyo (haddii aan si gaar ah laguu weydiisan luqad kale).
Ka dhig jawaabta mid kooban oo nuxur leh, kana fogow qoraalka aad u dheer ee aan loo baahnayn ilaa falanqayn qoto dheer lagaa codsado.

Awoodahaaga:
1. Falanqaynta Suuqyada (Crypto, Stocks, Forex, Commodities, Indices): Trend, Support/Resistance, iyo xaaladaha suurtagalka ah.
2. Wave Concept Trading: Wave structure, Entry zone, Take Profit (TP1/TP2), Stop Loss, iyo risk management kooban.
3. Fulinta Trade-ka: Order ticket cad (Pair, Side, Entry, SL, TP, Risk) iyo xusuusin haddii API-ga exchange-ka uusan xirnayn.
4. Baarista Coin-nada Mustaqbalka: Utility, catalysts, khataraha (volatility/unlocks/regulation), iyo xusuusin khatar maalgashi.
5. Luqadaha Swedish iyo English: Fasiraad iyo sharrax Af-Soomaali ah oo leh tusaalo maalinle ah.
6. Wararka (News): Dulmar kooban oo Af-Soomaali ah, saamaynta suuqa/arrinta, iyo kala saaridda xogta la xaqiijiyay.
7. Caawinta Guud: Farsamo, waxbarasho, iyo xallin dhibaato si toos ah.
"""


def send_telegram_message(chat_id, text):
    if not TELEGRAM_TOKEN:
        print("ERROR: Missing TELEGRAM_BOT_TOKEN or BOT_TOKEN environment variable")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        part = text[i : i + chunk_size]
        payload = {"chat_id": chat_id, "text": part}
        try:
            resp = requests.post(url, json=payload, timeout=20)
            print("Telegram sendMessage status:", resp.status_code, resp.text)
        except Exception as e:
            print("TELEGRAM_SEND_ERROR:", repr(e))


def execute_trade_hook(command_text):
    if not TRADE_EXECUTION_ENABLED:
        return None
    return f"[Trade Hook Active] Fariinta order-ka waa la diiwaangeliyay: {command_text}"


def discover_candidate_models(client):
    global _working_model
    candidates = []

    if _working_model:
        candidates.append(_working_model)

    fast_defaults = [
        "gemini-2.0-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-1.5-flash-8b",
        "gemini-1.5-flash",
    ]
    for d in fast_defaults:
        if d not in candidates:
            candidates.append(d)

    try:
        for m in client.models.list():
            raw_name = getattr(m, "name", "") or ""
            clean_name = raw_name.replace("models/", "").strip()
            if not clean_name:
                continue
            blocked_words = (
                "embedding",
                "imagen",
                "veo",
                "aqa",
                "bis",
                "tts",
                "live",
                "audio",
                "pro",
            )
            if any(w in clean_name.lower() for w in blocked_words):
                continue
            if "gemini" in clean_name.lower() and clean_name not in candidates:
                candidates.append(clean_name)
    except Exception as e:
        print("LIST_MODELS_WARNING:", repr(e))

    return candidates


def generate_ai_reply(user_text):
    global _working_model
    client = get_gemini_client()
    hook_note = execute_trade_hook(user_text)

    prompt = user_text
    if hook_note:
        prompt = f"{user_text}\n\n[Xogta Nidaamka: {hook_note}]"

    candidates = discover_candidate_models(client)
    last_error = None

    for model_name in candidates:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.35,
                    max_output_tokens=900,
                ),
            )
            reply = getattr(response, "text", None)
            if reply and reply.strip():
                _working_model = model_name
                print("SUCCESS_WITH_MODEL:", model_name)
                return reply.strip()
        except Exception as e:
            last_error = e
            print(f"MODEL_ATTEMPT_FAILED [{model_name}]:", repr(e))
            if _working_model == model_name:
                _working_model = None

    raise RuntimeError(f"All candidate models failed. Last error: {repr(last_error)}")


@app.route("/", methods=["GET"])
def home():
    return "AbdallaXIIR-bot is live", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    message = data.get("message") or data.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")

    if not chat_id or not text:
        return jsonify({"ok": True}), 200

    text = text.strip()
    if text == "/start":
        send_telegram_message(
            chat_id,
            "Ku soo dhawoow @AbdallaXiir_bot! Waxaan kaa caawin karaa:\n"
            "• Falanqaynta Crypto, Stocks, Forex & suuqyada kale\n"
            "• Wave Concept Trading (Entry, Take Profit & Stop Loss)\n"
            "• Baarista coin-nada mustaqbalka leh\n"
            "• Luqadaha Swedish iyo English oo lagu sharraxayo Af-Soomaali\n"
            "• Wararka (News) oo Af-Soomaali nidaamsan ah\n"
            "• Su'aalaha guud iyo qorshaynta trade-ka\n\n"
            "I weydii waxa aad rabto hadda!",
        )
        return jsonify({"ok": True}), 200

    try:
        ai_text = generate_ai_reply(text)
        send_telegram_message(chat_id, ai_text)
    except Exception as e:
        print("GEMINI_ERROR:", repr(e))
        send_telegram_message(
            chat_id,
            "Waan ka xunahay, AI-ga ayaa hadda culeys ku jira ama cilad ku meel gaar ah ayaa dhacday. Fadlan daqiiqad yar sug ka dibna mar kale isku day.",
        )

    return jsonify({"ok": True}), 200
