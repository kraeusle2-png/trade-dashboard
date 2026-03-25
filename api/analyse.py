from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

# ============================================================
# INDEX KONFIGURATION
# ============================================================
INDEX_LABELS = {
    "dax":"DAX","mdax":"MDAX","sdax":"SDAX",
    "nasdaq":"NASDAQ","dow":"Dow Jones","sp500":"S&P 500"
}

# FMP Symbol-Format: deutsche Aktien brauchen .DE oder .XETRA
FMP_SUFFIX = {
    "dax":".DE","mdax":".DE","sdax":".DE",
    "nasdaq":"","dow":"","sp500":""
}

# Vorausgewählte Kandidaten pro Index (Groq wählt vorab aus Wissen)
# Diese werden dann mit echten FMP-Daten verifiziert
PRESELECTED = {
    "dax": [
        "RHM","MUV2","CBK","DBK","SAP","SIE","BAS","ALV","BMW","MBG",
        "VOW3","ADS","BEI","HNR1","DTE","EOAN","RWE","HEI","MRK","IFX"
    ],
    "mdax": [
        "BOSS","DHER","LEG","PSM","SDF","TUI1","VNA","HAG","HLE","KGX",
        "NDA","SHL","SMHN","EVK","DWS","FRE","COP","AAD","AIXA","EMH"
    ],
    "sdax": [
        "BC8","DIC","DWNI","ECK","HAB","INH","KSB","MLP","NOEJ","GBF",
        "GYC","HHFA","EVT","FNTN","MOR","PBB","RRTL","WCH","GLJ","ADV"
    ],
    "nasdaq": [
        "NVDA","AAPL","MSFT","META","GOOGL","AMZN","TSLA","AVGO","AMD","NFLX",
        "ADBE","CRM","QCOM","TXN","LRCX","CRWD","DDOG","PLTR","PANW","MRVL"
    ],
    "dow": [
        "JPM","GS","UNH","HD","MCD","V","CAT","BA","HON","CVX",
        "XOM","AMGN","IBM","WMT","PG","JNJ","KO","AXP","TRV","VZ"
    ],
    "sp500": [
        "LMT","RTX","NOC","GD","F","GM","UBER","ABNB","SQ","SHOP",
        "PLTR","NET","SNOW","COIN","MRNA","PFE","REGN","VRTX","DAL","MAR"
    ]
}

# ============================================================
# FMP API HELPERS
# ============================================================
BASE = "https://financialmodelingprep.com/api/v3"

def fmp_get(path, api_key, params=None):
    """Generic FMP API call."""
    p = params or {}
    p["apikey"] = api_key
    qs = urllib.parse.urlencode(p)
    url = f"{BASE}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "TradeDashboard/4.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def get_quote(symbol, api_key):
    """Get real-time quote."""
    try:
        data = fmp_get(f"quote/{symbol}", api_key)
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        q = data[0]
        return {
            "price": q.get("price"),
            "change": q.get("changesPercentage"),
            "volume": q.get("volume"),
            "avgVolume": q.get("avgVolume"),
            "marketCap": q.get("marketCap"),
            "name": q.get("name", symbol)
        }
    except Exception:
        return None

def get_indicators(symbol, api_key):
    """Get technical indicators from FMP."""
    indicators = {}

    # RSI
    try:
        rsi_data = fmp_get(f"technical_indicator/daily/{symbol}", api_key, {"type": "rsi", "period": 14, "limit": 1})
        if rsi_data and isinstance(rsi_data, list) and len(rsi_data) > 0:
            indicators["rsi"] = round(rsi_data[0].get("rsi", 0), 1)
    except Exception:
        pass

    # MACD
    try:
        macd_data = fmp_get(f"technical_indicator/daily/{symbol}", api_key, {"type": "macd", "fastPeriod": 12, "slowPeriod": 26, "signalPeriod": 9, "limit": 1})
        if macd_data and isinstance(macd_data, list) and len(macd_data) > 0:
            macd_val = macd_data[0].get("macd", 0)
            signal_val = macd_data[0].get("signal", 0)
            indicators["macd"] = round(macd_val, 4)
            indicators["macdSignal"] = round(signal_val, 4)
            indicators["macdBullish"] = macd_val > signal_val
    except Exception:
        pass

    # SMA 20
    try:
        sma20_data = fmp_get(f"technical_indicator/daily/{symbol}", api_key, {"type": "sma", "period": 20, "limit": 1})
        if sma20_data and isinstance(sma20_data, list) and len(sma20_data) > 0:
            indicators["sma20"] = round(sma20_data[0].get("sma", 0), 2)
    except Exception:
        pass

    # SMA 50
    try:
        sma50_data = fmp_get(f"technical_indicator/daily/{symbol}", api_key, {"type": "sma", "period": 50, "limit": 1})
        if sma50_data and isinstance(sma50_data, list) and len(sma50_data) > 0:
            indicators["sma50"] = round(sma50_data[0].get("sma", 0), 2)
    except Exception:
        pass

    # EMA 20
    try:
        ema_data = fmp_get(f"technical_indicator/daily/{symbol}", api_key, {"type": "ema", "period": 20, "limit": 1})
        if ema_data and isinstance(ema_data, list) and len(ema_data) > 0:
            indicators["ema20"] = round(ema_data[0].get("ema", 0), 2)
    except Exception:
        pass

    # ADX
    try:
        adx_data = fmp_get(f"technical_indicator/daily/{symbol}", api_key, {"type": "adx", "period": 14, "limit": 1})
        if adx_data and isinstance(adx_data, list) and len(adx_data) > 0:
            indicators["adx"] = round(adx_data[0].get("adx", 0), 1)
    except Exception:
        pass

    return indicators

def rsi_signal(rsi):
    if rsi is None: return "unbekannt"
    if rsi < 30: return "ueberverkauft"
    if rsi < 40: return "schwach"
    if rsi > 70: return "ueberkauft"
    if rsi > 60: return "stark"
    return "neutral"

def calc_prescore(stock):
    """Calculate pre-score from indicators."""
    score = 0
    rsi = stock.get("rsi")
    vol_ratio = stock.get("volRatio", 1)
    above_sma20 = stock.get("aboveSMA20")
    sma20_dist = stock.get("sma20Dist", 0)
    macd_bull = stock.get("macdBullish")
    adx = stock.get("adx")
    change = stock.get("change", 0)

    # RSI (0-25)
    if rsi:
        if 40 <= rsi <= 60: score += 25
        elif 35 <= rsi <= 65: score += 18
        elif 30 <= rsi <= 70: score += 10

    # Volume (0-20)
    if vol_ratio >= 2.0: score += 20
    elif vol_ratio >= 1.5: score += 15
    elif vol_ratio >= 1.2: score += 10
    elif vol_ratio >= 1.0: score += 5

    # SMA20 (0-20)
    if above_sma20 is True:
        if 0 <= (sma20_dist or 0) <= 3: score += 20
        else: score += 10

    # MACD (0-15)
    if macd_bull is True: score += 15

    # ADX (0-10)
    if adx and adx > 25: score += 10

    # Change (0-10)
    if change and change > 0.5: score += 10
    elif change and change > 0: score += 5

    return min(100, score)

# ============================================================
# NEWS
# ============================================================
def fetch_news(query, news_key):
    if not news_key:
        return []
    try:
        url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote(query)}&sortBy=publishedAt&pageSize=3&apiKey={news_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "TradeDashboard/4.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
            return [a["title"] for a in d.get("articles", [])[:3]]
    except Exception:
        return []

# ============================================================
# GROQ KI
# ============================================================
def call_groq(prompt, groq_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1500
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {groq_key}"
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"]

# ============================================================
# MAIN HANDLER
# ============================================================
class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode())
            result = self._handle(body)
            self._respond(200, result)
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, code, data):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _handle(self, body):
        groq_key = os.environ.get("GROQ_API_KEY")
        fmp_key = os.environ.get("FMP_API_KEY")
        news_key = os.environ.get("NEWS_API_KEY")

        if not groq_key:
            raise Exception("GROQ_API_KEY fehlt in Vercel Environment Variables")
        if not fmp_key:
            raise Exception("FMP_API_KEY fehlt in Vercel Environment Variables")

        index = body.get("index", "dax")
        date = body.get("date", "heute")
        is_de = index in ["dax", "mdax", "sdax"]
        label = INDEX_LABELS[index]
        suffix = FMP_SUFFIX[index]
        tickers = PRESELECTED.get(index, PRESELECTED["dax"])

        # Step 1: Fetch quotes + indicators for all tickers
        results = []
        api_calls = 0

        for ticker in tickers:
            fmp_symbol = ticker + suffix
            try:
                # Quote (1 API call)
                quote = get_quote(fmp_symbol, fmp_key)
                api_calls += 1
                if not quote or not quote.get("price"):
                    continue

                price = quote["price"]
                change = round(quote.get("change") or 0, 2)
                volume = quote.get("volume") or 0
                avg_volume = quote.get("avgVolume") or 1
                vol_ratio = round(volume / avg_volume, 2) if avg_volume > 0 else 1.0
                currency = "EUR" if is_de else "USD"
                price_str = f"{price:.2f} €" if currency == "EUR" else f"${price:.2f}"

                # Indicators (up to 5 API calls per ticker)
                inds = get_indicators(fmp_symbol, fmp_key)
                api_calls += len(inds)

                rsi = inds.get("rsi")
                sma20 = inds.get("sma20")
                sma50 = inds.get("sma50")
                macd_bull = inds.get("macdBullish")
                adx = inds.get("adx")

                above_sma20 = price > sma20 if sma20 else None
                above_sma50 = price > sma50 if sma50 else None
                sma20_dist = round(((price - sma20) / sma20) * 100, 2) if sma20 else None

                stock = {
                    "ticker": ticker,
                    "name": quote.get("name", ticker),
                    "priceStr": price_str,
                    "price": price,
                    "change": change,
                    "volRatio": vol_ratio,
                    "rsi": rsi,
                    "rsiSignal": rsi_signal(rsi),
                    "aboveSMA20": above_sma20,
                    "aboveSMA50": above_sma50,
                    "sma20Dist": sma20_dist,
                    "macdBullish": macd_bull,
                    "adx": adx,
                    "ema20": inds.get("ema20"),
                    "atrPct": None,
                    "bbPct": None,
                    "stochK": None,
                    "tvRecommendation": "N/A",
                    "tvScore": None,
                    "buySignals": None,
                    "sellSignals": None,
                    "neutralSignals": None,
                    "dataSource": "FMP"
                }
                stock["preScore"] = calc_prescore(stock)
                results.append(stock)

            except Exception:
                continue

        if not results:
            raise Exception(f"Keine FMP-Daten verfuegbar. API-Aufrufe: {api_calls}. Bitte FMP_API_KEY pruefen.")

        # Sort by pre-score
        results.sort(key=lambda x: x["preScore"], reverse=True)
        top15 = results[:15]

        # News
        news_q = f"{label} Aktien Deutschland" if is_de else f"{label} stocks Wall Street"
        news = fetch_news(news_q, news_key)

        # Build KI prompt
        lines = []
        for s in top15:
            macd_str = f"MACD:{'bull' if s['macdBullish'] else 'bear'}" if s['macdBullish'] is not None else "MACD:n/a"
            adx_str = f"ADX:{s['adx']}" if s['adx'] else "ADX:n/a"
            sma20_str = f"SMA20:{'+' if (s.get('aboveSMA20') or False) else ''}{s.get('sma20Dist','?')}%" if s.get('sma20Dist') else "SMA20:n/a"
            lines.append(
                f"{s['ticker']} ({s['name']}): {s['priceStr']} | "
                f"Δ{'+' if s['change']>0 else ''}{s['change']}% | "
                f"Vol:{s['volRatio']}x | RSI:{s['rsi']}({s['rsiSignal']}) | "
                f"{sma20_str} | {macd_str} | {adx_str} | "
                f"Score:{s['preScore']}/100"
            )

        news_ctx = "\nNews:\n" + "\n".join(f"- {n}" for n in news) if news else ""
        einstieg = "09:15 Uhr" if is_de else "15:30 MEZ"

        prompt = f"""Du bist ein professioneller Intraday-Trader (20 Jahre Erfahrung).
Analysiere diese {label}-Aktien fuer Intraday-Long-Trades am {date}.
Alle Indikatoren sind ECHTE Daten von Financial Modeling Prep (FMP).

KANDIDATEN (sortiert nach Pre-Score):
{chr(10).join(lines)}
{news_ctx}

AUSWAHLKRITERIEN:
1. RSI idealerweise 40-65 (nicht ueberkauft, nicht ueberverkauft)
2. Volumen-Ratio > 1.2 (erhoehtes Handelsinteresse)
3. Kurs ueber SMA20 (Aufwaertstrend)
4. MACD bullish (Momentum bestaetigt)
5. ADX > 20 (Trend vorhanden)
6. CRV mindestens 1.5:1

TREFFERWAHRSCHEINLICHKEIT berechnen:
- RSI-Qualitaet: 25%
- MACD + ADX: 25%
- Volumen-Anomalie: 25%
- SMA-Trend + Katalysator: 25%

Waehle die 3 BESTEN Kandidaten.
Antworte NUR mit JSON-Array ohne Markdown ohne Backticks:
[{{"ticker":"RHM","name":"Rheinmetall","preis":"1.570 EUR",
"wahrscheinlichkeit":76,"einstieg":"{einstieg}","ziel":"+2.1%","stop":"-1.1%",
"crv":"1.9:1","katalysator":"RSI 54 neutral, MACD bullish, Vol 2.3x, SMA20+1.2%",
"risiko":"Gewinnmitnahmen nach Rally","index":"{label}"}}]
Genau 3 Titel. wahrscheinlichkeit als Integer."""

        response = call_groq(prompt, groq_key)
        clean = response.replace("```json", "").replace("```", "").strip()
        start = clean.find("[")
        end = clean.rfind("]") + 1
        if start == -1 or end == 0:
            raise Exception(f"Kein JSON in KI-Antwort: {clean[:300]}")

        stocks = json.loads(clean[start:end])

        # Enrich with real FMP data
        enriched = []
        for s in stocks:
            live = next((r for r in results if r["ticker"] == s["ticker"]), None)
            if live:
                s["preis"] = live["priceStr"]
                s["indikatoren"] = {
                    "rsi": live["rsi"],
                    "rsiSignal": live["rsiSignal"],
                    "volRatio": live["volRatio"],
                    "atrPct": live["atrPct"],
                    "aboveSMA20": live["aboveSMA20"],
                    "aboveSMA50": live["aboveSMA50"],
                    "aboveSMA200": None,
                    "sma20Dist": live["sma20Dist"],
                    "macdBullish": live["macdBullish"],
                    "bbPct": live["bbPct"],
                    "stochK": live["stochK"],
                    "adx": live["adx"],
                    "momentum": None,
                    "tvRecommendation": "FMP",
                    "tvScore": live["preScore"],
                    "buySignals": None,
                    "sellSignals": None,
                    "neutralSignals": None,
                    "preScore": live["preScore"],
                    "dataSource": "Financial Modeling Prep"
                }
            enriched.append(s)

        return {
            "stocks": enriched,
            "marketContext": {
                "idxName": label,
                "idxChange": None,
                "vix": None
            },
            "dataQuality": {
                "tickersAnalyzed": len(results),
                "tickersWithFullData": len(top15),
                "newsHeadlines": len(news),
                "apiCalls": api_calls,
                "dataSource": "Financial Modeling Prep (FMP)",
                "model": "Groq llama-3.3-70b",
                "timestamp": date
            }
        }

    def log_message(self, format, *args):
        pass
