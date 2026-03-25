from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

# ============================================================
# DATENQUALITÄTS-HINWEISE
# Quelle FMP-Dokumentation (verifiziert März 2026):
# - Deutsche Aktien: Symbol + .DE (XETRA)
# - Batch-Quote: /quote/SYM1,SYM2,SYM3 (spart API-Calls)
# - Indikatoren: End-of-Day Werte (nicht Intraday)
# - Free Tier: 250 Requests/Tag, 500MB/30 Tage
# ============================================================

INDEX_LABELS = {
    "dax":"DAX","mdax":"MDAX","sdax":"SDAX",
    "nasdaq":"NASDAQ","dow":"Dow Jones","sp500":"S&P 500"
}

IS_DE = {"dax","mdax","sdax"}

TICKERS = {
    "dax": [
        "RHM","MUV2","SAP","SIE","DTE","ALV","BAS","BMW","MBG","VOW3",
        "ADS","DBK","CBK","HEI","EOAN","RWE","BEI","HNR1","IFX","MRK",
        "FRE","AIR","CON","SHL","SRT3","SY1","VNA","ZAL","MTX","LIN",
        "QIA","PAH3","ENR","HAG","NDA","BAYN","P911","DTG","MAN","1COV"
    ],
    "mdax": [
        "BOSS","TUI1","LEG","SDF","HAG","HLE","PSM","SMHN","NDA","KGX",
        "EVK","DWS","DHER","COP","AAD","AIXA","EMH","FNTN","GBF","WCH"
    ],
    "sdax": [
        "BC8","DIC","DWNI","ECK","HAB","INH","KSB","MLP","NOEJ","GBF",
        "GYC","EVT","MOR","PBB","WCH","GLJ","ADV","SNH","SGCG","MWRK"
    ],
    "nasdaq": [
        "NVDA","AAPL","MSFT","META","GOOGL","AMZN","TSLA","AVGO","AMD","NFLX",
        "ADBE","CRM","QCOM","TXN","LRCX","CRWD","DDOG","PLTR","PANW","MRVL"
    ],
    "dow": [
        "JPM","GS","UNH","HD","MCD","V","CAT","BA","HON","CVX",
        "XOM","AMGN","IBM","WMT","PG","JNJ","KO","AXP","TRV","VZ",
        "MMM","DIS","NKE","MRK","CRM","CSCO","DOW","RTX","SHW","INTC"
    ],
    "sp500": [
        "LMT","RTX","NOC","GD","F","GM","UBER","ABNB","SQ","SHOP",
        "NET","SNOW","COIN","MRNA","PFE","REGN","VRTX","DAL","MAR","ENPH"
    ]
}

BASE = "https://financialmodelingprep.com/api/v3"

def fmp_request(path, api_key, params=None):
    p = dict(params or {})
    p["apikey"] = api_key
    qs = urllib.parse.urlencode(p)
    url = f"{BASE}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent":"TradeDashboard/4.2"})
    with urllib.request.urlopen(req, timeout=12) as r:
        raw = r.read().decode()
        data = json.loads(raw)
        # FMP returns error dict on auth fail
        if isinstance(data, dict) and data.get("Error Message"):
            raise Exception(f"FMP Auth Error: {data['Error Message']}")
        return data

def batch_quotes(symbols, api_key):
    """Fetch quotes for multiple symbols in one API call."""
    sym_str = ",".join(symbols)
    try:
        data = fmp_request(f"quote/{urllib.parse.quote(sym_str)}", api_key)
        if not isinstance(data, list):
            return {}
        return {q["symbol"]: q for q in data if q.get("price")}
    except Exception as e:
        return {}

def get_indicator(symbol, ind_type, period, api_key):
    """Get a single technical indicator value."""
    try:
        data = fmp_request(
            f"technical_indicator/daily/{urllib.parse.quote(symbol)}",
            api_key,
            {"type": ind_type, "period": period, "limit": 1}
        )
        if isinstance(data, list) and len(data) > 0:
            row = data[0]
            # Different indicators use different field names
            for field in [ind_type, "rsi", "sma", "ema", "macd", "adx", "signal"]:
                if field in row and row[field] is not None:
                    return round(float(row[field]), 2)
        return None
    except Exception:
        return None

def rsi_signal(rsi):
    if rsi is None: return "unbekannt"
    if rsi < 30: return "stark überverkauft ⚠"
    if rsi < 40: return "überverkauft"
    if rsi > 75: return "extrem überkauft ⚠"
    if rsi > 65: return "überkauft ⚠"
    if rsi > 55: return "stark bullish"
    if rsi > 45: return "neutral ✓"
    return "leicht bearish"

def prescore(rsi, vol_ratio, above_sma20, sma20_dist, macd_bull, adx, change):
    s = 0
    if rsi:
        if 45 <= rsi <= 62: s += 25
        elif 40 <= rsi <= 67: s += 17
        elif 35 <= rsi <= 72: s += 8
    vr = vol_ratio or 0
    if vr >= 2.0: s += 20
    elif vr >= 1.5: s += 14
    elif vr >= 1.2: s += 9
    elif vr >= 1.0: s += 4
    if above_sma20 is True:
        d = sma20_dist or 0
        if 0 <= d <= 2: s += 20
        elif d <= 5: s += 12
        else: s += 5
    if macd_bull is True: s += 15
    if adx:
        if adx > 30: s += 10
        elif adx > 20: s += 5
    ch = change or 0
    if ch > 1.0: s += 10
    elif ch > 0.3: s += 6
    elif ch > 0: s += 2
    return min(100, s)

def fetch_news(query, news_key):
    if not news_key: return []
    try:
        url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote(query)}&sortBy=publishedAt&pageSize=3&apiKey={news_key}"
        req = urllib.request.Request(url, headers={"User-Agent":"TradeDashboard/4.2"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
            return [a["title"] for a in d.get("articles",[])[:3]]
    except Exception:
        return []

def call_groq(prompt, groq_key):
    payload = json.dumps({
        "model":"llama-3.3-70b-versatile",
        "messages":[{"role":"user","content":prompt}],
        "temperature":0.3,"max_tokens":1500
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={"Content-Type":"application/json","Authorization":f"Bearer {groq_key}"}
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"]

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length",0))
            body = json.loads(self.rfile.read(n).decode())
            self._respond(200, self._handle(body))
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, code, data):
        self.send_response(code); self._cors()
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")

    def _handle(self, body):
        groq_key = os.environ.get("GROQ_API_KEY")
        fmp_key  = os.environ.get("FMP_API_KEY")
        news_key = os.environ.get("NEWS_API_KEY")
        if not groq_key: raise Exception("GROQ_API_KEY fehlt")
        if not fmp_key:  raise Exception("FMP_API_KEY fehlt")

        index = body.get("index","dax")
        date  = body.get("date","heute")
        is_de = index in IS_DE
        label = INDEX_LABELS[index]
        suffix = ".DE" if is_de else ""
        tickers = TICKERS.get(index, TICKERS["dax"])

        # Step 1: Batch quotes — 1 API call for all tickers
        fmp_symbols = [t + suffix for t in tickers]
        quotes = batch_quotes(fmp_symbols, fmp_key)

        if not quotes:
            # Diagnose: test with known-good symbol
            test = batch_quotes(["AAPL"], fmp_key)
            if not test:
                raise Exception("FMP_API_KEY ungültig oder API nicht erreichbar. Bitte Key in Vercel prüfen.")
            raise Exception(
                f"Keine Kursdaten für {label} mit Suffix '{suffix}'. "
                f"FMP kennt diese Symbole nicht. Möglicherweise sind {label}-Aktien "
                f"im kostenlosen FMP-Plan nicht verfügbar."
            )

        api_calls = 1
        results = []
        not_found = [t for t, sym in zip(tickers, fmp_symbols) if sym not in quotes]

        # Step 2: Indicators for found tickers (top 10 by vol ratio to save API calls)
        found_tickers = [(t, t+suffix) for t in tickers if (t+suffix) in quotes]

        # Sort by volume ratio first (pre-filter)
        def vol_sort(item):
            t, sym = item
            q = quotes[sym]
            vol = q.get("volume") or 0
            avg = q.get("avgVolume") or 1
            return vol / avg if avg > 0 else 0

        found_tickers.sort(key=vol_sort, reverse=True)
        top_tickers = found_tickers[:10]  # Only fetch indicators for top 10

        for ticker, fmp_sym in top_tickers:
            q = quotes[fmp_sym]
            price = q.get("price")
            if not price: continue

            change = round(q.get("changesPercentage") or 0, 2)
            volume = q.get("volume") or 0
            avg_vol = q.get("avgVolume") or 1
            vol_ratio = round(volume / avg_vol, 2) if avg_vol > 0 else 1.0
            name = q.get("name", ticker)

            # Fetch indicators
            rsi = get_indicator(fmp_sym, "rsi", 14, fmp_key); api_calls += 1
            sma20 = get_indicator(fmp_sym, "sma", 20, fmp_key); api_calls += 1
            sma50 = get_indicator(fmp_sym, "sma", 50, fmp_key); api_calls += 1

            # MACD (use ema as proxy if macd fails)
            macd_raw = get_indicator(fmp_sym, "macd", 12, fmp_key); api_calls += 1
            macd_bull = None
            if macd_raw is not None:
                macd_bull = macd_raw > 0  # positive MACD = bullish

            above_sma20 = (price > sma20) if sma20 else None
            above_sma50 = (price > sma50) if sma50 else None
            sma20_dist  = round(((price - sma20) / sma20) * 100, 2) if sma20 else None

            currency = "EUR" if is_de else "USD"
            price_str = f"{price:.2f} €" if currency == "EUR" else f"${price:.2f}"

            score = prescore(rsi, vol_ratio, above_sma20, sma20_dist, macd_bull, None, change)

            results.append({
                "ticker": ticker, "name": name, "fmpSym": fmp_sym,
                "priceStr": price_str, "price": price, "change": change,
                "volRatio": vol_ratio, "rsi": rsi, "rsiSignal": rsi_signal(rsi),
                "aboveSMA20": above_sma20, "aboveSMA50": above_sma50,
                "sma20Dist": sma20_dist, "macdBullish": macd_bull,
                "adx": None, "atrPct": None, "bbPct": None, "stochK": None,
                "tvRecommendation": "FMP", "tvScore": score,
                "buySignals": None, "sellSignals": None, "neutralSignals": None,
                "preScore": score, "dataSource": "Financial Modeling Prep"
            })

        if not results:
            raise Exception(
                f"FMP-Quotes gefunden ({len(quotes)}), aber Indikator-Abruf fehlgeschlagen. "
                f"Möglicherweise sind technische Indikatoren für {label} im Free-Plan gesperrt."
            )

        results.sort(key=lambda x: x["preScore"], reverse=True)
        top15 = results[:15]

        news_q = f"{label} Aktien Deutschland Börse" if is_de else f"{label} stocks Wall Street"
        news = fetch_news(news_q, news_key)

        lines = []
        for s in top15:
            macd_s = f"MACD:{'✓' if s['macdBullish'] else '✗'}" if s['macdBullish'] is not None else "MACD:n/a"
            sma_s  = f"SMA20:{'+' if (s['aboveSMA20'] or False) else ''}{s['sma20Dist']}%" if s['sma20Dist'] is not None else "SMA20:n/a"
            lines.append(
                f"{s['ticker']} ({s['name']}): {s['priceStr']} | "
                f"Δ{'+' if s['change']>0 else ''}{s['change']}% | "
                f"Vol:{s['volRatio']}x | RSI:{s['rsi']}({s['rsiSignal'].replace(' ⚠','').replace(' ✓','')}) | "
                f"{sma_s} | {macd_s} | Score:{s['preScore']}/100"
            )

        einstieg = "09:15 Uhr" if is_de else "15:30 MEZ"
        news_ctx = "\nNews:\n" + "\n".join(f"- {n}" for n in news) if news else ""

        prompt = f"""Du bist ein professioneller Intraday-Trader (20 Jahre Erfahrung).
Analysiere diese {label}-Aktien für Intraday-Long-Trades am {date}.
HINWEIS: Alle Indikatoren sind End-of-Day Werte von Financial Modeling Prep.

KANDIDATEN ({len(top15)} analysiert, {len(not_found)} nicht gefunden):
{chr(10).join(lines)}
{news_ctx}

KRITERIEN:
1. RSI 40-65 bevorzugt (nicht überkauft/überverkauft)
2. Volumen-Ratio > 1.2
3. Kurs über SMA20
4. MACD positiv/bullish
5. CRV mindestens 1.5:1

TREFFERWAHRSCHEINLICHKEIT (0-85% realistisch):
- RSI-Qualität 40-65: 25%
- MACD + Trend: 25%
- Volumen: 25%
- Katalysator: 25%

Wähle die 3 BESTEN. Antworte NUR mit JSON-Array ohne Markdown:
[{{"ticker":"RHM","name":"Rheinmetall","preis":"1.486 EUR",
"wahrscheinlichkeit":72,"einstieg":"{einstieg}","ziel":"+1.8%","stop":"-1.0%",
"crv":"1.8:1","katalysator":"RSI 53, MACD bull, Vol 1.9x, SMA20+1.2%",
"risiko":"EOD-Daten — Intraday kann abweichen","index":"{label}"}}]
Genau 3 Titel. wahrscheinlichkeit als Integer 50-82."""

        resp = call_groq(prompt, groq_key)
        clean = resp.replace("```json","").replace("```","").strip()
        s, e = clean.find("["), clean.rfind("]")+1
        if s < 0 or e <= 0:
            raise Exception(f"Kein JSON: {clean[:200]}")
        stocks = json.loads(clean[s:e])

        enriched = []
        for stk in stocks:
            live = next((r for r in results if r["ticker"]==stk["ticker"]), None)
            if live:
                stk["preis"] = live["priceStr"]
                stk["indikatoren"] = {
                    "rsi": live["rsi"], "rsiSignal": live["rsiSignal"],
                    "volRatio": live["volRatio"], "atrPct": None,
                    "aboveSMA20": live["aboveSMA20"], "aboveSMA50": live["aboveSMA50"],
                    "aboveSMA200": None, "sma20Dist": live["sma20Dist"],
                    "macdBullish": live["macdBullish"], "bbPct": None,
                    "stochK": None, "adx": None, "momentum": None,
                    "tvRecommendation": "FMP", "tvScore": live["preScore"],
                    "buySignals": None, "sellSignals": None, "neutralSignals": None,
                    "preScore": live["preScore"], "dataSource": "Financial Modeling Prep"
                }
            enriched.append(stk)

        warnings = [
            "ℹ️ Indikatoren = End-of-Day Werte (Vortag), nicht Intraday-Daten",
            f"ℹ️ {len(not_found)} Ticker nicht in FMP gefunden: {', '.join(not_found[:8]) if not_found else 'keine'}"
        ]

        return {
            "stocks": enriched,
            "marketContext": {"idxName": label, "idxChange": None, "vix": None},
            "dataQuality": {
                "tickersAnalyzed": len(results),
                "quotesFound": len(quotes),
                "tickersNotFound": len(not_found),
                "notFoundList": not_found,
                "newsHeadlines": len(news),
                "apiCalls": api_calls,
                "dataSource": "Financial Modeling Prep (FMP)",
                "dataType": "End-of-Day (Vortag)",
                "warnings": warnings,
                "model": "Groq llama-3.3-70b",
                "timestamp": date
            }
        }

    def log_message(self, *a): pass
