from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

try:
    from tradingview_ta import TA_Handler, Interval, Exchange
    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False

# ============================================================
# TICKER POOLS — maximale Abdeckung
# ============================================================
TICKERS = {
    "dax": [
        "RHM","MUV2","CBK","DBK","SAP","SIE","BAS","ALV","BMW","MBG",
        "VOW3","ADS","BEI","HNR1","MTX","DTE","EOAN","RWE","HEI","MRK",
        "SHL","FRE","AIR","BNR","CON","DTG","ENR","HAG","IFX","LIN",
        "NDA","QIA","SRT3","SY1","VNA","ZAL","1COV","HFG","MAN","PAH3"
    ],
    "mdax": [
        "AIR","BOSS","COP","DHER","DWS","ENR","FRE","HAG","HLE","HOT",
        "IFX","KGX","LEG","NDA","PSM","SDF","SHL","SMHN","TUI1","VNA",
        "AAD","AIXA","BC8","CLIQ","DIC","DLG","DWNI","ECK","EMH","EVT",
        "FNTN","GBF","GYC","HAB","HHFA","INH","KSB","MLP","NOEJ","HOMG",
        "GLJ","EVK","DEQ","MOR","NDX1","NTCO","PBB","RRTL","WCH","SFQ"
    ],
    "sdax": [
        "AAD","AIXA","ARND","B5A","BC8","CLIQ","DIC","DLG","DNKA","DWNI",
        "ECK","EMH","EVT","FNTN","GBF","GYC","HAB","HHFA","HHX","HOMG",
        "INH","KSB","MLP","MWRK","NOEJ","GLJ","EVK","DEQ","MOR","NDX1",
        "NTCO","PBB","RRTL","WCH","SFQ","ACX","AOF","BIO3","DBAN","ELGX",
        "JUVE","LBK","MBB","OHB","TLX","GBF","MBB","SNH","SGCG","ADV"
    ],
    "nasdaq": [
        "NVDA","AAPL","MSFT","META","GOOGL","AMZN","TSLA","AVGO","QCOM","AMD",
        "NFLX","ADBE","CRM","CSCO","TXN","MU","PYPL","INTC","LRCX","KLAC",
        "MRVL","AMAT","SNPS","CDNS","MCHP","ADI","NXPI","CRWD","DDOG","NET",
        "SNOW","PLTR","COIN","RBLX","SHOP","SQ","UBER","ABNB","DASH","ZM",
        "OKTA","DOCU","ASML","PANW","FTNT","WDAY","TEAM","MDB","ESTC","GTLB"
    ],
    "dow": [
        "JPM","GS","MS","BAC","WMT","HD","MCD","KO","PG","JNJ",
        "UNH","V","AXP","IBM","CAT","BA","MMM","HON","CVX","XOM",
        "AMGN","CRM","DIS","DOW","GE","MRK","NKE","RTX","TRV","VZ"
    ],
    "sp500": [
        "LMT","RTX","NOC","GD","HII","F","GM","DIS","UBER","ABNB",
        "SQ","SHOP","ZM","PLTR","COIN","RBLX","SNAP","NET","BABA","NIO",
        "DKNG","MGM","DAL","UAL","CCL","RCL","MAR","HLT","ENPH","FSLR",
        "PLUG","CHPT","EVGO","RIVN","LCID","HOOD","PENN","CZR","NCLH","AAL",
        "SEDG","BE","BLDP","FCEL","RUN","MRNA","BNTX","PFE","REGN","VRTX"
    ]
}

INDEX_LABELS = {
    "dax": "DAX", "mdax": "MDAX", "sdax": "SDAX",
    "nasdaq": "NASDAQ", "dow": "Dow Jones", "sp500": "S&P 500"
}

EXCHANGE_MAP = {
    "dax": "XETRA", "mdax": "XETRA", "sdax": "XETRA",
    "nasdaq": "NASDAQ", "dow": "NYSE", "sp500": "NYSE"
}

SCREENER_MAP = {
    "dax": "germany", "mdax": "germany", "sdax": "germany",
    "nasdaq": "america", "dow": "america", "sp500": "america"
}

INTERVAL_MAP = {
    "1d": Interval.INTERVAL_1_DAY if TV_AVAILABLE else "1d"
}

def get_tv_data(ticker, exchange, screener):
    """Fetch TradingView indicators for a single ticker."""
    if not TV_AVAILABLE:
        return None
    try:
        handler = TA_Handler(
            symbol=ticker,
            exchange=exchange,
            screener=screener,
            interval=Interval.INTERVAL_1_DAY,
            timeout=8
        )
        analysis = handler.get_analysis()
        ind = analysis.indicators
        summary = analysis.summary

        # RSI signal text
        rsi = ind.get("RSI", None)
        rsi_signal = "neutral"
        if rsi is not None:
            if rsi < 30: rsi_signal = "ueberverkauft"
            elif rsi < 40: rsi_signal = "schwach"
            elif rsi > 70: rsi_signal = "ueberkauft"
            elif rsi > 60: rsi_signal = "stark"
            else: rsi_signal = "neutral"

        close = ind.get("close", None)
        sma20 = ind.get("SMA20", None)
        sma50 = ind.get("SMA50", None)
        sma200 = ind.get("SMA200", None)
        volume = ind.get("volume", None)
        volume_avg = ind.get("average_volume", None) or ind.get("volume_avg", None)

        above_sma20 = (close > sma20) if (close and sma20) else None
        above_sma50 = (close > sma50) if (close and sma50) else None
        above_sma200 = (close > sma200) if (close and sma200) else None
        sma20_dist = round(((close - sma20) / sma20) * 100, 2) if (close and sma20) else None
        vol_ratio = round(volume / volume_avg, 2) if (volume and volume_avg and volume_avg > 0) else None

        # ATR
        atr = ind.get("ATR", None)
        atr_pct = round((atr / close) * 100, 2) if (atr and close) else None

        # MACD
        macd = ind.get("MACD.macd", None)
        macd_signal = ind.get("MACD.signal", None)
        macd_bullish = (macd > macd_signal) if (macd is not None and macd_signal is not None) else None

        # Bollinger
        bb_upper = ind.get("BB.upper", None)
        bb_lower = ind.get("BB.lower", None)
        bb_pct = None
        if close and bb_upper and bb_lower and (bb_upper - bb_lower) > 0:
            bb_pct = round(((close - bb_lower) / (bb_upper - bb_lower)) * 100, 1)

        # Stochastic RSI
        stoch_k = ind.get("Stoch.K", None)
        stoch_d = ind.get("Stoch.D", None)

        # ADX
        adx = ind.get("ADX", None)

        # Momentum
        mom = ind.get("Mom", None)

        # TradingView recommendation
        tv_rec = summary.get("RECOMMENDATION", "NEUTRAL")
        buy_count = summary.get("BUY", 0)
        sell_count = summary.get("SELL", 0)
        neutral_count = summary.get("NEUTRAL", 0)
        total = buy_count + sell_count + neutral_count
        tv_score = round((buy_count / total) * 100) if total > 0 else 50

        # Pre-score calculation
        pre_score = 0
        if rsi is not None:
            if 40 <= rsi <= 60: pre_score += 25
            elif 35 <= rsi <= 65: pre_score += 18
            elif 30 <= rsi <= 70: pre_score += 10
        if vol_ratio is not None:
            if vol_ratio >= 2.0: pre_score += 20
            elif vol_ratio >= 1.5: pre_score += 15
            elif vol_ratio >= 1.2: pre_score += 10
            elif vol_ratio >= 1.0: pre_score += 5
        if above_sma20 is True:
            if sma20_dist is not None and 0 <= sma20_dist <= 3: pre_score += 20
            elif sma20_dist is not None: pre_score += 10
        if macd_bullish is True: pre_score += 15
        if adx is not None and adx > 25: pre_score += 10
        if mom is not None and mom > 0: pre_score += 10
        pre_score = min(100, pre_score)

        # Price formatting
        currency = "EUR" if screener == "germany" else "USD"
        price_str = f"{close:.2f} €" if currency == "EUR" else f"${close:.2f}"

        # Change calculation
        change = ind.get("change", None)
        change_str = f"+{change:.2f}%" if change and change > 0 else f"{change:.2f}%" if change else "0.00%"

        return {
            "ticker": ticker,
            "priceStr": price_str,
            "price": close,
            "change": round(change, 2) if change else 0,
            "changeStr": change_str,
            "volRatio": vol_ratio,
            "rsi": round(rsi, 1) if rsi else None,
            "rsiSignal": rsi_signal,
            "atrPct": atr_pct,
            "aboveSMA20": above_sma20,
            "aboveSMA50": above_sma50,
            "aboveSMA200": above_sma200,
            "sma20Dist": sma20_dist,
            "macdBullish": macd_bullish,
            "bbPct": bb_pct,
            "stochK": round(stoch_k, 1) if stoch_k else None,
            "adx": round(adx, 1) if adx else None,
            "momentum": round(mom, 2) if mom else None,
            "tvRecommendation": tv_rec,
            "tvScore": tv_score,
            "buySignals": buy_count,
            "sellSignals": sell_count,
            "neutralSignals": neutral_count,
            "preScore": pre_score
        }
    except Exception as e:
        return None


def fetch_news(query, news_key):
    """Fetch news headlines."""
    if not news_key:
        return []
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://newsapi.org/v2/everything?q={encoded}&sortBy=publishedAt&pageSize=3&apiKey={news_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "TradeDashboard/3.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            return [a["title"] for a in data.get("articles", [])[:3]]
    except:
        return []


def call_groq(prompt, groq_key):
    """Call Groq API."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1500
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {groq_key}"
        }
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"]


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode())
            result = self._handle(body)
            self.send_response(200)
            self._set_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        except Exception as e:
            self.send_response(500)
            self._set_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _handle(self, body):
        groq_key = os.environ.get("GROQ_API_KEY")
        news_key = os.environ.get("NEWS_API_KEY")

        if not groq_key:
            raise Exception("GROQ_API_KEY fehlt in Vercel Environment Variables")
        if not TV_AVAILABLE:
            raise Exception("tradingview-ta nicht installiert — requirements.txt prüfen")

        index = body.get("index", "dax")
        date = body.get("date", "heute")
        is_de = index in ["dax", "mdax", "sdax"]

        exchange = EXCHANGE_MAP[index]
        screener = SCREENER_MAP[index]
        tickers = TICKERS.get(index, TICKERS["dax"])
        index_label = INDEX_LABELS[index]

        # Fetch TradingView data for all tickers
        results = []
        for ticker in tickers:
            data = get_tv_data(ticker, exchange, screener)
            if data:
                results.append(data)

        if not results:
            raise Exception(f"Keine TradingView-Daten verfügbar für {index_label}")

        # Sort by pre-score and take top 15 for KI
        results.sort(key=lambda x: x["preScore"], reverse=True)
        top_candidates = results[:15]

        # Fetch news
        news_query = f"{index_label} Aktien Deutschland Boerse" if is_de else f"{index_label} stocks Wall Street"
        news = fetch_news(news_query, news_key)

        # Build context for KI
        stock_lines = []
        for s in top_candidates:
            tv_rec = s.get("tvRecommendation", "NEUTRAL")
            line = (
                f"{s['ticker']}: {s['priceStr']} | "
                f"Δ {s['changeStr']} | "
                f"Vol-Ratio {s['volRatio']}x | "
                f"RSI {s['rsi']} ({s['rsiSignal']}) | "
                f"ATR {s['atrPct']}% | "
                f"SMA20 {'+' if s['aboveSMA20'] else ''}{s['sma20Dist']}% | "
                f"MACD {'bullish' if s['macdBullish'] else 'bearish'} | "
                f"ADX {s['adx']} | "
                f"TV: {tv_rec} ({s['buySignals']}↑/{s['sellSignals']}↓) | "
                f"Score {s['preScore']}/100"
            )
            stock_lines.append(line)

        news_context = "\nAktuelle News:\n" + "\n".join(f"- {n}" for n in news) if news else ""
        einstieg = "09:15 Uhr" if is_de else "15:30 MEZ"

        prompt = f"""Du bist ein professioneller Intraday-Trader mit 20 Jahren Erfahrung.
Analysiere die folgenden vorgefilterten {index_label}-Aktien fuer Intraday-Long-Trades am {date}.
Alle Indikatoren stammen direkt von TradingView und sind exakt berechnet.

KANDIDATEN (sortiert nach technischem Pre-Score):
{chr(10).join(stock_lines)}
{news_context}

AUSWAHLKRITERIEN:
1. TradingView-Signal idealerweise BUY oder STRONG_BUY
2. RSI zwischen 40-65 (nicht ueberkauft)
3. Volumen-Ratio > 1.2
4. Kurs ueber SMA20 (Aufwaertstrend)
5. MACD bullish
6. ADX > 20 (Trend vorhanden)
7. CRV mindestens 1.5:1 (Stop = 1x ATR, Ziel = 2x ATR)

TREFFERWAHRSCHEINLICHKEIT:
- TradingView-Signal: 30%
- RSI + MACD + ADX: 30%
- Volumen-Ratio: 20%
- Katalysator/News: 20%

Waehle die 3 BESTEN Kandidaten.
Antworte NUR mit reinem JSON-Array ohne Markdown ohne Backticks:
[{{
  "ticker": "RHM",
  "name": "Rheinmetall",
  "preis": "1.570 EUR",
  "wahrscheinlichkeit": 76,
  "einstieg": "{einstieg}",
  "ziel": "+2.1%",
  "stop": "-1.1%",
  "crv": "1.9:1",
  "katalysator": "TV STRONG_BUY, RSI 54, Vol 2.3x, MACD bullish",
  "risiko": "Gewinnmitnahmen nach Rally",
  "index": "{index_label}"
}}]
Genau 3 Titel. wahrscheinlichkeit als Integer."""

        # Call Groq
        response_text = call_groq(prompt, groq_key)
        clean = response_text.replace("```json", "").replace("```", "").strip()

        # Extract JSON
        start = clean.find("[")
        end = clean.rfind("]") + 1
        if start == -1 or end == 0:
            raise Exception(f"Kein JSON in Antwort: {clean[:300]}")

        stocks = json.loads(clean[start:end])

        # Enrich with real TradingView data
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
                    "aboveSMA200": live["aboveSMA200"],
                    "sma20Dist": live["sma20Dist"],
                    "macdBullish": live["macdBullish"],
                    "bbPct": live["bbPct"],
                    "stochK": live["stochK"],
                    "adx": live["adx"],
                    "momentum": live["momentum"],
                    "tvRecommendation": live["tvRecommendation"],
                    "tvScore": live["tvScore"],
                    "buySignals": live["buySignals"],
                    "sellSignals": live["sellSignals"],
                    "neutralSignals": live["neutralSignals"],
                    "preScore": live["preScore"]
                }
            enriched.append(s)

        return {
            "stocks": enriched,
            "dataQuality": {
                "tickersAnalyzed": len(results),
                "tickersWithFullData": len(top_candidates),
                "newsHeadlines": len(news),
                "dataSource": "TradingView (tradingview-ta)",
                "model": "Groq llama-3.3-70b",
                "tvAvailable": TV_AVAILABLE,
                "timestamp": date
            }
        }

    def log_message(self, format, *args):
        pass
