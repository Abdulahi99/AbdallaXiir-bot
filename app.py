import os
import time
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
_active_model = "gemini-3.5-flash-lite"


def get_gemini_client():
    global _client
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable")
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


SYSTEM_INSTRUCTION = """
Waxaad tahay caawiye AI ah oo aad u caqli badan, xirfad sare leh, oo luqadaha si qoto dheer u yaqaanna una shaqeeya @AbdallaXiir_bot.

Xeerarka luqadda iyo qoraalka:
- Had iyo jeer ku qor Af-Soomaali dabiici ah, cad, naxwe ahaan sax ah, oo leh xarrago iyo macne sugan — haddii isticmaaluhu si cad u codsado Swedish ama English, ugu jawaab luqaddaas si heer sare ah.
- Markaad sharraxayso erayo Swedish ama English ah, u fasir si sax ah oo bixi tusaalooyin maalinle ah oo la fahmi karo.
- Ha joojin ama ha kala goyn jawaabta bartamaha; mar walba dhammaystir falanqaynta, tixraacyada, iyo gunaanadka.
- Ha isticmaalin calaamado Markdown oo dhiman (sida `**` aan xirnayn) ama qoraal isku qasan.

Awoodahaaga qoto dheer:
1. Falanqaynta Suuqyada (Crypto, Stocks, Forex, Commodities, Indices): Samee taxliil nidaamsan (Trend, Support/Resistance, Momentum, iyo xaaladaha kor iyo hoos).
2. Wave Concept Trading: Falanqee Impulse (1-2-3-4-5) iyo Corrective (A-B-C) — sheeg Wave count/structure, Entry zone, Stop Loss, TP1/TP2, iyo maareynta khatarta.
3. Baarista Coin-nada Mustaqbalka & Long-Term: Falanqee aasaaska mashruuca (utility, adoption, tokenomics/unlocks, catalysts), khataraha, iyo istaraatijiyadda soogalitaanka (sida DCA ama qaybsashada meelaha soo laabashada), adigoo mar walba xusaya in maalgashigu leeyahay khatar.
4. Trade Execution Plan: Haddii la dalbado qorshe trade, qor Pair, Side, Entry, SL, TP, iyo Risk %, adigoo xusaya haddii API-ga exchange-ka uusan weli toos ugu xirnayn.
5. Luqadaha (Af-Soomaali, Swedish, English): Turjumaad sax ah, sharrax naxwe/ereyo, iyo isbarbardhig macne oo caqli leh.
6. Wararka WatcherGuru & Suuqyada: U qor wararka si nidaamsan (Dulmar Warka Af-Soomaali, Saamaynta Suuqa/Crypto, iyo Xogta La Xaqiijiyay vs Waxa Isbeddeli Kara).
7. Su'aalaha Guud, IT & Farsamada: Ka jawaab su'aal kasta si deggan, faahfaahsan, oo xallin leh.
"""


def send_telegram_message(chat_id, text):
    if not TELEGRAM_TOKEN:
        print("ERROR: Missing TELEGRAM_BOT_TOKEN or BOT_TOKEN environment variable")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    clean_text = (text or "").strip()
    if not clean_text:
        return

    chunk_size = 3900
    for i in range(0, len(clean_text), chunk_size):
        part = clean_text[i : i + chunk_size]
        payload = {
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=25)
            if resp.status_code != 200:
                print("Telegram sendMessage non-200:", resp.status_code, resp.text)
        except Exception as e:
            print("TELEGRAM_SEND_ERROR:", repr(e))


def execute_trade_hook(command_text):
    if not TRADE_EXECUTION_ENABLED:
        return None
    return f"[Trade Hook Active] Order command logged: {command_text}"


def _build_model_queue(skip_models):
    raw_candidates = [
        _active_model,
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-2.5-flash-lite",
    ]
    queue = []
    seen = set()
    for m in raw_candidates:
        if m and m not in seen and m not in skip_models:
            seen.add(m)
            queue.append(m)
    return queue


def _is_quota_or_not_found(err_text):
    markers = (
        "404",
        "NOT_FOUND",
        "429",
        "QuotaFailure",
        "RESOURCE_EXHAUSTED",
        "no longer available",
    )
    return any(k in err_text for k in markers)


def generate_ai_reply(prompt_text):
    global _active_model
    client = get_gemini_client()
    skip_models = set()
    last_error = None

    for _ in range(2):
        queue = _build_model_queue(skip_models)
        if not queue:
            break

        for model_name in queue:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.35,
                        max_output_tokens=1800,
                    ),
                )
                reply = getattr(response, "text", None)
                if reply and reply.strip():
                    _active_model = model_name
                    return reply.strip()
            except Exception as e:
                last_error = e
                err_str = repr(e)
                print(f"MODEL_ATTEMPT_FAILED [{model_name}]:", err_str)
                if _is_quota_or_not_found(err_str):
                    skip_models.add(model_name)
                if _active_model == model_name:
                    _active_model = "gemini-3.5-flash-lite"

        if skip_models and len(skip_models) >= 3:
            time.sleep(0.6)

    raise RuntimeError(f"All models failed. Last error: {repr(last_error)}")


def _extract_forward_source(message):
    forward_origin = message.get("forward_origin") or {}
    origin_type = forward_origin.get("type")
    if origin_type == "channel":
        chat_obj = forward_origin.get("chat") or {}
        return chat_obj.get("username") or chat_obj.get("title") or "Channel"
    if origin_type == "user":
        sender = forward_origin.get("sender_user") or {}
        return sender.get("username") or sender.get("first_name") or "User"

    fwd_from_chat = message.get("forward_from_chat") or {}
    if fwd_from_chat:
        return fwd_from_chat.get("username") or fwd_from_chat.get("title") or "Channel"
    return None


@app.route("/", methods=["GET"])
def home():
    return "AbdallaXIIR-bot is live", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    message = data.get("message") or data.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or message.get("caption")

    if not chat_id:
        return jsonify({"ok": True}), 200

    if not text:
        if message.get("photo") or message.get("document") or message.get("video"):
            send_telegram_message(
                chat_id,
                "Waxaan arkay fayl/sawir aan lahayn qoraal (caption). Fadlan iigu soo dir qoraalka warka ama su'aashaada si aan Af-Soomaali ugu falanqeeyo.",
            )
        return jsonify({"ok": True}), 200

    text = text.strip()
    if text == "/start":
        send_telegram_message(
            chat_id,
            "Ku soo dhawoow @AbdallaXiir_bot! Waxaan kaa caawin karaa wax kasta oo nidaamsan oo dhameystiran:\n"
            "• WatcherGuru & Wararka Suuqyada: I soo forward garee warka WatcherGuru ama isticmaal /wg [qoraalka] si aan kuugu soo saaro Af-Soomaali nidaamsan\n"
            "• Falanqaynta Crypto, Stocks, Forex & suuqyada kale\n"
            "• Wave Concept Trading (Entry, Stop Loss & TP1/TP2)\n"
            "• Baarista coin-nada mustaqbalka leh & istaraatijiyadda long-term\n"
            "• Luqadaha Af-Soomaali, Swedish & English oo si qoto dheer loo sharraxo\n"
            "• Su'aalaha guud, IT/farsamada, iyo xallinta dhibaatooyinka\n\n"
            "I weydii su'aashaada ama i soo forward garee warka hadda!",
        )
        return jsonify({"ok": True}), 200

    forward_source = _extract_forward_source(message)
    is_wg_command = text.lower().startswith("/wg")

    if is_wg_command:
        news_body = text[3:].strip()
        if not news_body:
            send_telegram_message(
                chat_id,
                "Fadlan ku dar qoraalka warka ka dib /wg, tusaale:\n/wg Bitcoin ETF inflows hit record high...",
            )
            return jsonify({"ok": True}), 200
        prompt_to_send = (
            "Fadlan warkan (WatcherGuru / Market News) si sax ah ugu turjun oo ugu falanqee Af-Soomaali nidaamsan "
            "(1. Dulmar Warka, 2. Saamaynta Suuqa/Crypto, 3. Xogta La Xaqiijiyay vs Waxa Isbeddeli Kara):\n\n"
            f"{news_body}"
        )
    elif forward_source:
        prompt_to_send = (
            f"Warkan waxaa laga soo forward gareeyay isha: {forward_source}. "
            "Fadlan si sax ah ugu turjun oo ugu falanqee Af-Soomaali nidaamsan "
            "(1. Dulmar Warka, 2. Saamaynta Suuqa/Crypto, 3. Xogta La Xaqiijiyay vs Waxa Isbeddeli Kara):\n\n"
            f"{text}"
        )
    else:
        hook_note = execute_trade_hook(text)
        prompt_to_send = f"{text}\n\n[System Note: {hook_note}]" if hook_note else text

    try:
        ai_text = generate_ai_reply(prompt_to_send)
        send_telegram_message(chat_id, ai_text)
    except Exception as e:
        print("GEMINI_ERROR:", repr(e))
        send_telegram_message(
            chat_id,
            "Waan ka xunahay, nidaamka AI-ga ayaa hadda la kulmay cilad ku meel gaar ah ama xaddid isticmaal. Fadlan daqiiqad yar sug ka dibna mar kale isku day.",
        )

    return jsonify({"ok": True}), 200
