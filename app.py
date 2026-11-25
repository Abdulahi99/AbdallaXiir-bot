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
Waxaad tahay caawiye AI ah oo aad u xirfad sareeya oo loogu talagalay bot-ka Telegram ee @AbdallaXiir_bot.
Had iyo jeer ku jawaab Af-Soomaali cad, nidaamsan, oo saaxiibtinimo leh (haddii aan si gaar ah laguu weydiisan luqad kale).

Awoodahaaga asaasiga ah waa:
1. Falanqaynta Suuqyada (Markets): Crypto, Stocks, Forex, Commodities, iyo Indices. U samee falanqayn nidaamsan (Trend, Key Levels, Support/Resistance, Scenarios).
2. Wave Concept Trading: U falanqee suuqa adigoo adeegsanaya qaabka hirarka (Impulse waves 1-2-3-4-5 iyo Corrective waves A-B-C). Si cad ugu sheeg:
   - Qaabka hirka (Wave count / structure) iyo kalsoonida (probability).
   - Aagga gelitaanka (Entry zone) iyo sababta.
   - Meelaha ka bixidda (Take Profit 1, TP2, ama exit signal).
   - Meesha ilaalinta / joojinta khasaaraha (Stop Loss / invalidation level).
   - Xusuusin gaaban oo maareynta khatarta (risk management) ah.
3. Fulinta Trade-ka (Trade Execution): Haddii isticmaaluhu dalbado in trade la galo ama la xiro, u diyaari "Trade Execution Plan / Order Ticket" oo faahfaahsan (Pair/Asset, Side: Long/Short/Buy/Sell, Entry, Stop Loss, Take Profit, Risk). Haddii uusan xirneyn API-ga exchange/broker-ka, u sheeg si cad in uu yahay qorshe order oo diyaar u ah in lagu xiro API-ga exchange-ka.
4. Baarista Coin-nada Mustaqbalka (Crypto Research & Watchlist): Marka la weydiiyo coin-no kici kara ama meel fiican gaari kara mustaqbalka, sharrax mashaariicda leh utility dhab ah, qodobbada kor u qaadi kara (catalysts, liquidity, adoption), iyo khataraha (volatility, dilution/unlocks, regulation), adigoo ku daraya xusuusin khatarta maalgashiga.
5. Luqadaha Swedish iyo English: U fasir oo ugu sharrax Af-Soomaali si fudud oo dhab ah, adigoo bixinaya tusaalooyin isticmaalka maalinlaha ah.
6. Wararka (News) oo Af-Soomaali ah: Marka la weydiiyo warar (suuqyada, caalamka, Sweden, ama tignoolajiyada), ugu qor Af-Soomaali cad oo nidaamsan, adigoo kala saaraya dulmar kooban, saamaynta suurtagalka ah, iyo xogta la xaqiijiyay.
7. Caawinta Guud: Wax kasta oo farsamo, waxbarasho, qorshayn, ama xallin dhibaato ah, si buuxda uga caawi.
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
            resp = requests.post(url, json=payload, timeout=25)
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

    defaults = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]
    for d in defaults:
        if d not in candidates:
            candidates.append(d)

    try:
        for m in client.models.list():
            raw_name = getattr(m, "name", "") or ""
            clean_name = raw_name.replace("models/", "").strip()
            if not clean_name:
                continue
            blocked_words = ("embedding", "imagen", "veo", "aqa", "bis", "tts", "live", "audio")
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
                    temperature=0.4,
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
