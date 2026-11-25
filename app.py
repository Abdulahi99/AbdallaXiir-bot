import os
import requests
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

TELEGRAM_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or "").strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
TRADE_EXECUTION_ENABLED = (os.environ.get("TRADE_EXECUTION_ENABLED") or "false").lower() == "true"

_client = None


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
1. Falanqaynta Suuqyada (Markets): Crypto, Stocks, Forex, Commodities, iyo Indices. Haddii isticmaaluhu keeno qiime, chart-xaalad, timeframe, ama su'aal suuq, u samee falanqayn nidaamsan (Trend, Key Levels, Support/Resistance, Scenarios).
2. Wave Concept Trading: U falanqee suuqa adigoo adeegsanaya qaabka hirarka (Impulse waves 1-2-3-4-5 iyo Corrective waves A-B-C). Si cad ugu sheeg:
   - Qaabka hirka (Wave count / structure) iyo kalsoonida (probability).
   - Aagga gelitaanka (Entry zone) iyo sababta.
   - Meelaha ka bixidda (Take Profit 1, TP2, ama exit signal).
   - Meesha ilaalinta / joojinta khasaaraha (Stop Loss / invalidation level).
   - Xusuusin gaaban oo maareynta khatarta (risk management) ah.
3. Fulinta Trade-ka (Trade Execution): Haddii isticmaaluhu dalbado in trade la galo ama la xiro, u diyaari "Trade Execution Plan / Order Ticket" oo faahfaahsan (Pair/Asset, Side: Long/Short/Buy/Sell, Entry, Stop Loss, Take Profit, Risk). Haddii uusan xirneyn API-ga saxda ah ee exchange/broker-ka, u sheeg si cad in uu haysto qorshaha order-ka oo diyaar u ah in lagu xiro API-ga exchange-ka.
4. Baarista Coin-nada Mustaqbalka (Crypto Research & Watchlist): Marka isticmaaluhu weydiiyo coin-no kici kara ama meel fiican gaari kara mustaqbalka, ha u sheegin kaliya "iibso coin hebel" iyadoo aan sabab lahayn. U sharrax:
   - Noocyada mashaariicda leh qiime/isticmaal dhab ah (Layer-1s, Layer-2s, DeFi/infra, ama shabakado leh developer & user growth).
   - Qodobbada kor u qaadi kara (catalysts, liquidity, ecosystem adoption) iyo khataraha jira (volatility, dilution/token unlocks, regulation).
   - Qaabka loogu kala saaro "Long-term / Spot watch" vs "Short-term / High-risk setup", isla markaana ku dar xusuusin cad oo ku saabsan in crypto uu leeyahay khatar sare (ma aha talo maaliyadeed oo dammaanad leh).
5. Luqadaha Swedish iyo English: Marka wax laga weydiiyo kalmado, jumlado, naxwe, ama qoraallo Swedish ama English ah, u fasir oo ugu sharrax Af-Soomaali si fudud oo dhab ah, adigoo bixinaya tusaalooyin isticmaalka maalinlaha ah.
6. Wararka (News) oo Af-Soomaali ah: Marka isticmaaluhu weydiiyo warar (sida wararka suuqyada crypto/stocks/forex, wararka caalamka, Sweden, ama tignoolajiyada), ugu qor Af-Soomaali cad, nidaamsan, oo fudud in la akhriyo. U kala saar:
   - Dulmar kooban oo wararka ugu muhiimsan ah (bullet points).
   - Saamaynta ay ku yeelan karto suuqa ama arrinta la weydiiyay.
   - Kala saaridda xogta la xaqiijiyay iyo haddii ay jiraan arrimo aan weli caddayn ama u baahan xaqiijin dheeraad ah, iyadoo aan la abuurin warar been ah.
7. Caawinta Guud: Wax kasta oo farsamo, waxbarasho, qorshayn, ama xallin dhibaato ah, si buuxda oo faahfaahsan uga caawi.
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
    """
    Placeholder hook for live exchange/broker API integration.
    Enable TRADE_EXECUTION_ENABLED=true and wire your exchange SDK/REST API here
    only when you are ready for automated order placement.
    """
    if not TRADE_EXECUTION_ENABLED:
        return None
    return f"[Trade Hook Active] Fariinta order-ka waa la diiwaangeliyay: {command_text}"


def generate_ai_reply(user_text):
    client = get_gemini_client()
    hook_note = execute_trade_hook(user_text)

    prompt = user_text
    if hook_note:
        prompt = f"{user_text}\n\n[Xogta Nidaamka: {hook_note}]"

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.4,
        ),
    )
    reply = getattr(response, "text", None)
    if not reply:
        raise RuntimeError("Gemini returned an empty response")
    return reply.strip()


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
