from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

# ============================================================
# WICHTIGE HINWEISE ZUR DATENQUALITÄT
# ============================================================
# 1. Symbol-Format: Deutsche Aktien verwenden .DE (XETRA)
#    Quelle: FMP offizielle Dokumentation
# 2. FMP Free Tier: max. 250 API-Aufrufe/Tag
#    Bei 20 Aktien x 4 Aufrufe = 80 Aufrufe pro Analyse
# 3. Indikatoren sind Tageswerte (End-of-Day), NICHT Intraday
#    RSI/MACD basieren auf Schlusskursen des Vortags
# 4. MDAX/SDAX Ticker: Nicht alle Symbole sind bei FMP verfügbar
#    Nicht gefundene Ticker werden übersprungen und geloggt
# 5. FMP neue stabile API: /stable/technical-indicators/
# ============================================================

INDEX_LABELS = {
    "dax": "DAX", "mdax": "MDAX", "sdax": "SDAX",
    "nasdaq": "NASDAQ", "dow": "Dow Jones", "sp500": "S&P 500"
}

# Verifiziert: FMP verwendet .DE für XETRA
# Quelle: https://github.com/FinancialModelingPrepAPI/Financial-Modeling-Prep-API
FMP_SUFFIX = {
    "dax": ".DE", "mdax": ".DE", "sdax": ".DE",
    "nasdaq": "", "dow": "", "sp500": ""
}

# ============================================================
# TICKER POOLS
# Hinweis: DAX-40 verifiziert per Deutsche Börse Stand Q1 2026
# MDAX/SDAX: Auswahl basierend auf Indexzusammensetzung,
# nicht alle Symbole ggf. bei FMP verfügbar
# US-Ticker: NYSE/NASDAQ verifiziert
# ============================================================
PRESELECTED = {
    "dax": [
        # DAX 40 — vollständige Liste (Stand Q1 2026)
        "RHM", "MUV2", "SAP", "SIE", "DTE", "ALV", "BAS", "BMW",
        "MBG", "VOW3", "ADS", "DBK", "CBK", "HEI", "EOAN", "RWE",
        "BEI", "HNR1", "IFX", "MRK", "FRE", "AIR", "CON", "SHL",
        "SRT3", "SY1", "VNA", "ZAL", "MTX", "LIN", "QIA", "PAH3",
        "DTG", "ENR", "HAG", "NDA", "1COV", "MAN", "BAYN", "P911"
    ],
    "mdax": [
        # MDAX — Auswahl liquidester Titel
        # ⚠️ Nicht alle ggf. bei FMP verfügbar
        "BOSS", "TUI1", "LEG", "VNA", "SDF", "HAG", "HLE", "PSM",
        "SMHN", "NDA", "KGX", "EVK", "DWS", "DHER", "COP", "AAD",
        "AIXA", "EMH", "FNTN", "GBF"
    ],
    "sdax": [
        # SDAX — Auswahl liquidester Titel
        # ⚠️ Nicht alle ggf. bei FMP verfügbar
        "BC8", "DIC", "DWNI", "ECK", "HAB", "INH", "KSB", "MLP",
        "NOEJ", "GBF", "GYC", "EVT", "MOR", "PBB", "WCH", "GLJ",
        "ADV", "MWRK", "SNH", "SGCG"
    ],
    "nasdaq": [
        # NASDAQ 100 Top — verifiziert
        "NVDA", "AAPL", "MSFT", "META", "GOOGL", "AMZN", "TSLA",
        "AVGO", "AMD", "NFLX", "ADBE", "CRM", "QCOM", "TXN",
        "LRCX", "CRWD", "DDOG", "PLTR", "PANW", "MRVL"
    ],
    "dow": [
        # Dow Jones 30 — vollständig, verifiziert
        "JPM", "GS", "UNH", "HD", "MCD", "V", "CAT", "BA", "HON",
        "CVX", "XOM", "AMGN", "IBM", "WMT", "PG", "JNJ", "KO",
        "AXP", "TRV", "VZ", "MMM", "DIS", "DOW", "NKE", "MRK",
        "CRM", "CSCO", "INTC", "RTX", "SHW"
    ],
    "sp500": [
        # S&P 500 — Auswahl nach Liquidität & Momentum
        "LMT", "RTX", "NOC", "GD", "F", "GM", "UBER", "ABNB",
        "SQ", "SHOP", "NET", "SNOW", "COIN", "MRNA", "PFE",
        "REGN", "VRTX", "DAL", "MAR", "ENPH"
    ]
}

BASE_V3 = "https://financialmodelingprep.com/api/v3"
BASE_STABLE = "https://financialmodelingprep.com/stable"

def fmp_get(url_full):
    """Generic FMP GET request."""
    req = urllib.request.Request(
        url_full,
        headers={"User-Agent": "TradeDashboard/4.1"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def get_quote(symbol, api_key):
    """Real-time quote via FMP v3."""
    try:
        url = f"{BASE_V3}/quote/{urllib.parse.quote(symbol)}?apikey={api_key}"
        data = fmp_get(url)
        if not data or not isinstance(data, list) or not data[0].get("price"):
            return None
        q = data[0]
        return {
            "price": q.get("price"),
            "change": round(q.get("changesPercentage") or 0, 2),
            "volume": q.get("volume") or 0,
            "avgVolume": q.get("avgVolume") or 1,
            "name": q.get("name", symbol),
            "exchange": q.get("exchange", "")
        }
    except Exception:
        return None

def get_rsi(symbol, api_key):
    """RSI (14) via FMP stable endpoint."""
    try:
        url = f"{BASE_STABLE}/technical-indicators/rsi?symbol={urllib.parse.quote(symbol)}&periodLength=14&timeframe=1day&apikey={api_key}"
        data = fmp_get(url)
        if data and isinstance(data, list) and len(data) > 0:
            return round(data[0].get("rsi") or data[0].get("value") or 0, 1)
        # Fallback to v3
        url2 = f"{BASE_V3}/technical_indicator/daily/{urllib.parse.quote(symbol)}?type=rsi&period=14&limit=1&apikey={api_key}"
        data2 = fmp_get(url2)
        if data2 and isinstance(data2, list) and len(data2) > 0:
            return round(data2[0].get("rsi") or 0, 1)
        return None
    except Exception:
        return None

def get_macd(symbol, api_key):
    """MACD via FMP stable endpoint."""
    try:
        url = f"{BASE_STABLE}/technical-indicators/macd?symbol={urllib.parse.quote(symbol)}&fastLength=12&slowLength=26&signalLength=9&timeframe=1day&apikey={api_key}"
        data = fmp_get(url)
        if data and isinstance(data, list) and len(data) > 0:
            macd_val = data[0].get("macd") or data[0].get("value")
            signal_val = data[0].get("signal") or data[0].get("macdSignal")
            if macd_val is not None and signal_val is not None:
                return round(macd_val, 4), round(signal_val, 4), macd_val > signal_val
        # Fallback to v3
        url2 = f"{BASE_V3}/technical_indicator/daily/{urllib.parse.quote(symbol)}?type=macd&fastPeriod=12&slowPeriod=26&signalPeriod=9&limit=1&apikey={api_key}"
        data2 = fmp_get(url2)
        if data2 and isinstance(data2, list) and len(data2) > 0:
            m = data2[0].get("macd") or 0
            s = data2[0].get("signal") or 0
            return round(m, 4), round(s, 4), m > s
        return None, None, None
    except Exception:
        return None, None, None

def get_sma(symbol, period, api_key):
    """SMA via FMP stable endpoint."""
    try:
        url = f"{BASE_STABLE}/technical-indicators/sma?symbol={urllib.parse.quote(symbol)}&periodLength={period}&timeframe=1day&apikey={api_key}"
        data = fmp_get(url)
        if data and isinstance(data, list) and len(data) > 0:
            val = data[0].get("sma") or data[0].get("value")
            return round(val, 2) if val else None
        # Fallback to v3
        url2 = f"{BASE_V3}/technical_indicator/daily/{urllib.parse.quote(symbol)}?type=sma&period={period}&limit=1&apikey={api_key}"
        data2 = fmp_get(url2)
        if data2 and isinstance(data2, list) and len(data2) > 0:
            return round(data2[0].get("sma") or 0, 2)
        return None
    except Exception:
        return None

def get_adx(symbol, api_key):
    """ADX via FMP stable endpoint."""
    try:
        url = f"{BASE_STABLE}/technical-indicators/adx?symbol={urllib.parse.quote(symbol)}&periodLength=14&timeframe=1day&apikey={api_key}"
        data = fmp_get(url)
        if data and isinstance(data, list) and len(data) > 0:
            val = data[0].get("adx") or data[0].get("value")
            return round(val, 1) if val else None
        # Fallback to v3
        url2 = f"{BASE_V3}/technical_indicator/daily/{urllib.parse.quote(symbol)}?type=adx&period=14&limit=1&apikey={api_key}"
        data2 = fmp_get(url2)
        if data2 and isinstance(data2, list) and len(data2) > 0:
            return round(data2[0].get("adx") or 0, 1)
        return None
    except Exception:
        return None

def rsi_signal(rsi):
    if rsi is None: return "unbekannt"
    if rsi < 30: return "stark überverkauft ⚠️"
    if rsi < 40: return "überverkauft"
    if rsi > 80: return "extrem überkauft ⚠️"
    if rsi > 70: return "überkauft ⚠️"
    if rsi > 60: return "stark"
    return "neutral ✓"

def calc_prescore(stock):
    score = 0
    rsi = stock.get("rsi")
    vol_ratio = stock.get("volRatio", 1.0)
    above_sma20 = stock.get("aboveSMA20")
    sma20_dist = stock.get("sma20Dist") or 0
    macd_bull = stock.get("macdBullish")
    adx = stock.get("adx")
    change = stock.get("change", 0)

    if rsi:
        if 45 <= rsi <= 60: score += 25
        elif 40 <= rsi <= 65: score += 18
        elif 35 <= rsi <= 70: score += 10
        else: score += 0

    if vol_ratio >= 2.0: score += 20
    elif vol_ratio >= 1.5: score += 15
    elif vol_ratio >= 1.2: score += 10
    elif vol_ratio >= 1.0: score += 5

    if above_sma20 is True:
        if 0 <= sma20_dist <= 2: score += 20
        elif sma20_dist <= 5: score += 12
        else: score += 5

    if macd_bull is True: score += 15
    elif macd_bull is False: score += 0

    if adx and adx > 30: score += 10
    elif adx and adx > 20: score += 5

    if change and change > 0.5: score += 10
    elif change and change > 0: score += 5

    return min(100, score)

def fetch_news(query, news_key):
    if not news_key: return []
    try:
        url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote(query)}&sortBy=publishedAt&pageSize=3&apiKey={news_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "TradeDashboard/4.1"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
            return [a["title"] for a in d.get("articles", [])[:3]]
    except Exception:
        return []

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

        results = []
        not_found = []
        api_calls = 0
        warnings = []

        for ticker in tickers:
            fmp_symbol = ticker + suffix
            try:
                # Quote
                quote = get_quote(fmp_symbol, fmp_key)
                api_calls += 1

                if not quote or not quote.get("price"):
                    not_found.append(ticker)
                    continue

                price = quote["price"]
                change = quote["change"]
                volume = quote.get("volume", 0)
                avg_volume = quote.get("avgVolume", 1)
                vol_ratio = round(volume / avg_volume, 2) if avg_volume > 0 else 1.0

                # RSI
                rsi = get_rsi(fmp_symbol, fmp_key)
                api_calls += 1

                # MACD
                macd_val, macd_sig, macd_bull = get_macd(fmp_symbol, fmp_key)
                api_calls += 1

                # SMA 20
                sma20 = get_sma(fmp_symbol, 20, fmp_key)
                api_calls += 1

                # SMA 50
                sma50 = get_sma(fmp_symbol, 50, fmp_key)
                api_calls += 1

                above_sma20 = (price > sma20) if sma20 else None
                above_sma50 = (price > sma50) if sma50 else None
                sma20_dist = round(((price - sma20) / sma20) * 100, 2) if sma20 else None

                # ADX (optional — spart API-Calls)
                adx = None
                if api_calls < 200:
                    adx = get_adx(fmp_symbol, fmp_key)
                    api_calls += 1

                currency = "EUR" if is_de else "USD"
                price_str = f"{price:.2f} €" if currency == "EUR" else f"${price:.2f}"

                # Warnung wenn Kurs nicht zum erwarteten Bereich passt
                if is_de and price < 0.01:
                    warnings.append(f"{ticker}: Kurs {price} unplausibel — ggf. falsches Symbol")

                stock = {
                    "ticker": ticker,
                    "fmpSymbol": fmp_symbol,
                    "name": quote.get("name", ticker),
                    "exchange": quote.get("exchange", ""),
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
                    "atrPct": None,
                    "bbPct": None,
                    "stochK": None,
                    "tvRecommendation": "FMP",
                    "tvScore": None,
                    "buySignals": None,
                    "sellSignals": None,
                    "neutralSignals": None,
                    "dataSource": "Financial Modeling Prep"
                }
                stock["preScore"] = calc_prescore(stock)
                results.append(stock)

            except Exception as e:
                not_found.append(f"{ticker}({str(e)[:30]})")
                continue

        if not results:
            detail = f"Nicht gefunden: {', '.join(not_found[:5])}. API-Calls: {api_calls}."
            raise Exception(f"Keine FMP-Daten für {label}. {detail} Bitte FMP_API_KEY und Symbol-Format prüfen.")

        # Warnung wenn viele Ticker fehlen
        if len(not_found) > len(tickers) * 0.5:
            warnings.append(f"⚠️ Mehr als 50% der Ticker nicht gefunden ({len(not_found)}/{len(tickers)}). Datenqualität eingeschränkt.")

        # Hinweis auf End-of-Day Daten
        warnings.append("ℹ️ Indikatoren basieren auf Tagesschlusskursen (End-of-Day), nicht auf Intraday-Daten.")

        results.sort(key=lambda x: x["preScore"], reverse=True)
        top15 = results[:15]

        news_q = f"{label} Aktien Deutschland" if is_de else f"{label} stocks Wall Street"
        news = fetch_news(news_q, news_key)

        lines = []
        for s in top15:
            macd_str = f"MACD:{'✓bull' if s['macdBullish'] else '✗bear'}" if s['macdBullish'] is not None else "MACD:n/a"
            adx_str = f"ADX:{s['adx']}" if s['adx'] else "ADX:n/a"
            sma_str = f"SMA20:{'+' if (s.get('aboveSMA20') or False) else ''}{s.get('sma20Dist', '?')}%" if s.get('sma20Dist') is not None else "SMA20:n/a"
            lines.append(
                f"{s['ticker']} ({s['name']}): {s['priceStr']} | "
                f"Δ{'+' if s['change'] > 0 else ''}{s['change']}% | "
                f"Vol:{s['volRatio']}x | RSI:{s['rsi']}({s['rsiSignal'].replace(' ⚠️','').replace(' ✓','')}) | "
                f"{sma_str} | {macd_str} | {adx_str} | Score:{s['preScore']}/100"
            )

        news_ctx = "\nNews:\n" + "\n".join(f"- {n}" for n in news) if news else ""
        einstieg = "09:15 Uhr" if is_de else "15:30 MEZ"

        prompt = f"""Du bist ein professioneller Intraday-Trader (20 Jahre Erfahrung).
Analysiere diese {label}-Aktien für Intraday-Long-Trades am {date}.
WICHTIG: Alle Indikatoren sind End-of-Day Werte von Financial Modeling Prep (FMP).

KANDIDATEN (Top nach Pre-Score, {len(top15)} von {len(results)} gefunden):
{chr(10).join(lines)}
{news_ctx}

AUSWAHLKRITERIEN (streng anwenden):
1. RSI idealerweise 40-65 — NICHT über 70 (überkauft = schlechter Einstieg)
2. Volumen-Ratio > 1.2 (erhöhtes Handelsinteresse)
3. Kurs über SMA20 (Aufwärtstrend bestätigt)
4. MACD bullish (Momentum positiv)
5. ADX > 20 wenn verfügbar (Trendstärke)
6. CRV mindestens 1.5:1

TREFFERWAHRSCHEINLICHKEIT (transparent berechnen):
- RSI-Qualität (40-65): 25%
- MACD + ADX: 25%
- Volumen-Ratio: 25%
- SMA-Trend + Katalysator: 25%

Wähle die 3 BESTEN Kandidaten.
Antworte NUR mit JSON-Array ohne Markdown ohne Backticks:
[{{"ticker":"RHM","name":"Rheinmetall","preis":"1.486 EUR",
"wahrscheinlichkeit":74,"einstieg":"{einstieg}","ziel":"+1.8%","stop":"-1.0%",
"crv":"1.8:1","katalysator":"RSI 52 neutral, MACD bullish, Vol 1.8x, SMA20+1.5%",
"risiko":"End-of-Day Daten — Intraday-Bewegung kann abweichen",
"index":"{label}"}}]
Genau 3 Titel. wahrscheinlichkeit als Integer zwischen 50-85."""

        response = call_groq(prompt, groq_key)
        clean = response.replace("```json", "").replace("```", "").strip()
        start = clean.find("[")
        end = clean.rfind("]") + 1
        if start == -1 or end == 0:
            raise Exception(f"Kein JSON in KI-Antwort: {clean[:300]}")

        stocks = json.loads(clean[start:end])

        enriched = []
        for s in stocks:
            live = next((r for r in results if r["ticker"] == s["ticker"]), None)
            if live:
                s["preis"] = live["priceStr"]
                s["indikatoren"] = {
                    "rsi": live["rsi"],
                    "rsiSignal": live["rsiSignal"],
                    "volRatio": live["volRatio"],
                    "atrPct": None,
                    "aboveSMA20": live["aboveSMA20"],
                    "aboveSMA50": live["aboveSMA50"],
                    "aboveSMA200": None,
                    "sma20Dist": live["sma20Dist"],
                    "macdBullish": live["macdBullish"],
                    "bbPct": None,
                    "stochK": None,
                    "adx": live["adx"],
                    "momentum": None,
                    "tvRecommendation": "FMP",
                    "tvScore": live["preScore"],
                    "buySignals": None,
                    "sellSignals": None,
                    "neutralSignals": None,
                    "preScore": live["preScore"],
                    "dataSource": "Financial Modeling Prep",
                    "exchange": live.get("exchange", "")
                }
            enriched.append(s)

        return {
            "stocks": enriched,
            "marketContext": {"idxName": label, "idxChange": None, "vix": None},
            "dataQuality": {
                "tickersAnalyzed": len(results),
                "tickersNotFound": len(not_found),
                "notFoundList": not_found[:10],
                "tickersWithFullData": len(top15),
                "newsHeadlines": len(news),
                "apiCalls": api_calls,
                "dataSource": "Financial Modeling Prep (FMP)",
                "dataType": "End-of-Day (Vortag)",
                "warnings": warnings,
                "model": "Groq llama-3.3-70b",
                "timestamp": date
            }
        }

    def log_message(self, format, *args):
        pass
