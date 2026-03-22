from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

# TradingView import
try:
    from tradingview_ta import TA_Handler, Interval
    TV_AVAILABLE = True
except Exception:
    TV_AVAILABLE = False

# ============================================================
# TICKER POOLS
# ============================================================
TICKERS = {
    "dax": [
        "RHM","MUV2","CBK","DBK","SAP","SIE","BAS","ALV","BMW","MBG",
        "VOW3","ADS","BEI","HNR1","MTX","DTE","EOAN","RWE","HEI","MRK",
        "SHL","FRE","AIR","BNR","CON","ENR","HAG","IFX","LIN","NDA",
        "SRT3","SY1","VNA","ZAL","1COV","HFG","PAH3","QIA","DTG","MAN"
    ],
    "mdax": [
        "AIR","BOSS","COP","DHER","DWS","ENR","FRE","HAG","HLE","HOT",
        "IFX","KGX","LEG","NDA","PSM","SDF","SHL","SMHN","TUI1","VNA",
        "AAD","AIXA","BC8","DIC","DLG","DWNI","ECK","EMH","EVT","FNTN",
        "GBF","GYC","HAB","HHFA","INH","KSB","MLP","NOEJ","EVK","DEQ",
        "MOR","NDX1","NTCO","PBB","RRTL","WCH","SFQ","GLJ","HOMG","CLIQ"
    ],
    "sdax": [
        "AAD","AIXA","ARND","B5A","BC8","DIC","DLG","DNKA","DWNI","ECK",
        "EMH","EVT","FNTN","GBF","GYC","HAB","HHFA","HOMG","INH","KSB",
        "MLP","NOEJ","GLJ","EVK","DEQ","MOR","NDX1","NTCO","PBB","RRTL",
        "WCH","SFQ","ACX","AOF","BIO3","DBAN","ELGX","JUVE","LBK","MBB",
        "OHB","TLX","SNH","ADV","MWRK","HHX","CLIQ","SGCG","B5A","ARND"
    ],
    "nasdaq": [
        "NVDA","AAPL","MSFT","META","GOOGL","AMZN","TSLA","AVGO","QCOM","AMD",
        "NFLX","ADBE","CRM","CSCO","TXN","MU","PYPL","INTC","LRCX","KLAC",
        "MRVL","AMAT","SNPS","CDNS","MCHP","ADI","NXPI","CRWD","DDOG","NET",
        "SNOW","PLTR","COIN","SHOP","SQ","UBER","ABNB","DASH","ZM","OKTA",
        "PANW","FTNT","WDAY","TEAM","MDB","GTLB","ASML","DOCU","ESTC","SPLK"
    ],
    "dow": [
        "JPM","GS","MS","BAC","WMT","HD","MCD","KO","PG","JNJ",
        "UNH","V","AXP","IBM","CAT","BA","MMM","HON","CVX","XOM",
        "AMGN","CRM","DIS","DOW","GE","MRK","NKE","RTX","TRV","VZ"
    ],
    "sp500": [
        "LMT","RTX","NOC","GD","HII","F","GM","DIS","UBER","ABNB",
        "SQ","SHOP","ZM","PLTR","COIN","RBLX","SNAP","NET","NIO","DKNG",
        "MGM","DAL","UAL","CCL","RCL","MAR","HLT","ENPH","FSLR","PLUG",
        "CHPT","EVGO","RIVN","LCID","HOOD","PENN","CZR","NCLH","AAL","SEDG",
        "MRNA","BNTX","PFE","REGN","VRTX","BIIB","ILMN","IDXX","MTD","TMO"
    ]
}

INDEX_LABELS = {
    "dax":"DAX","mdax":"MDAX","sdax":"SDAX",
    "nasdaq":"NASDAQ","dow":"Dow Jones","sp500":"S&P 500"
}
EXCHANGE_MAP = {
    "dax":"XETRA","mdax":"XETRA","sdax":"XETRA",
    "nasdaq":"NASDAQ","dow":"NYSE","sp500":"NYSE"
}
SCREENER_MAP = {
    "dax":"germany","mdax":"germany","sdax":"germany",
    "nasdaq":"america","dow":"america","sp500":"america"
}
YAHOO_SUFFIX = {
    "dax":".DE","mdax":".DE","sdax":".DE",
    "nasdaq":"","dow":"","sp500":""
}

# ============================================================
# RSI + ATR + MA Berechnung (Yahoo Fallback)
# ============================================================
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains += diff
        else: losses += abs(diff)
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def calc_atr(highs, lows, closes, period=14):
    if len(highs) < period + 1:
        return None
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period

def calc_ma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def rsi_signal(rsi):
    if rsi is None: return "unbekannt"
    if rsi < 30: return "ueberverkauft"
    if rsi < 40: return "schwach"
    if rsi > 70: return "ueberkauft"
    if rsi > 60: return "stark"
    return "neutral"

# ============================================================
# TradingView Daten
# ============================================================
def get_tv_data(ticker, exchange, screener):
    if not TV_AVAILABLE:
        return None
    try:
        h = TA_Handler(
            symbol=ticker, exchange=exchange,
            screener=screener, interval=Interval.INTERVAL_1_DAY, timeout=8
        )
        a = h.get_analysis()
        ind = a.indicators
        summ = a.summary
        close = ind.get("close")
        if not close:
            return None
        rsi = ind.get("RSI")
        sma20 = ind.get("SMA20")
        sma50 = ind.get("SMA50")
        sma200 = ind.get("SMA200")
        atr = ind.get("ATR")
        volume = ind.get("volume")
        vol_avg = ind.get("average_volume") or ind.get("volume_avg")
        macd = ind.get("MACD.macd")
        macd_sig = ind.get("MACD.signal")
        adx = ind.get("ADX")
        mom = ind.get("Mom")
        bb_upper = ind.get("BB.upper")
        bb_lower = ind.get("BB.lower")
        stoch_k = ind.get("Stoch.K")
        change = ind.get("change")

        atr_pct = round((atr/close)*100,2) if atr and close else None
        above_sma20 = close > sma20 if sma20 else None
        above_sma50 = close > sma50 if sma50 else None
        above_sma200 = close > sma200 if sma200 else None
        sma20_dist = round(((close-sma20)/sma20)*100,2) if sma20 else None
        vol_ratio = round(volume/vol_avg,2) if volume and vol_avg and vol_avg>0 else None
        macd_bull = macd > macd_sig if macd is not None and macd_sig is not None else None
        bb_pct = round(((close-bb_lower)/(bb_upper-bb_lower))*100,1) if bb_upper and bb_lower and (bb_upper-bb_lower)>0 else None

        tv_rec = summ.get("RECOMMENDATION","NEUTRAL")
        buy_c = summ.get("BUY",0)
        sell_c = summ.get("SELL",0)
        neut_c = summ.get("NEUTRAL",0)
        total = buy_c + sell_c + neut_c
        tv_score = round((buy_c/total)*100) if total>0 else 50

        # Pre-score
        score = 0
        if rsi:
            if 40<=rsi<=60: score+=25
            elif 35<=rsi<=65: score+=18
            elif 30<=rsi<=70: score+=10
        if vol_ratio:
            if vol_ratio>=2: score+=20
            elif vol_ratio>=1.5: score+=15
            elif vol_ratio>=1.2: score+=10
            elif vol_ratio>=1: score+=5
        if above_sma20 is True:
            score += 20 if sma20_dist and 0<=sma20_dist<=3 else 10
        if macd_bull is True: score+=15
        if adx and adx>25: score+=10
        if mom and mom>0: score+=10

        currency = "EUR" if screener=="germany" else "USD"
        price_str = f"{close:.2f} €" if currency=="EUR" else f"${close:.2f}"
        change_val = round(change,2) if change else 0

        return {
            "ticker":ticker, "priceStr":price_str, "price":close,
            "change":change_val, "volRatio":vol_ratio, "rsi":round(rsi,1) if rsi else None,
            "rsiSignal":rsi_signal(rsi), "atrPct":atr_pct,
            "aboveSMA20":above_sma20, "aboveSMA50":above_sma50, "aboveSMA200":above_sma200,
            "sma20Dist":sma20_dist, "macdBullish":macd_bull, "bbPct":bb_pct,
            "stochK":round(stoch_k,1) if stoch_k else None,
            "adx":round(adx,1) if adx else None, "momentum":round(mom,2) if mom else None,
            "tvRecommendation":tv_rec, "tvScore":tv_score,
            "buySignals":buy_c, "sellSignals":sell_c, "neutralSignals":neut_c,
            "preScore":min(100,score), "dataSource":"TradingView"
        }
    except Exception:
        return None

# ============================================================
# Yahoo Finance Fallback
# ============================================================
def get_yahoo_data(ticker, suffix, screener):
    try:
        yt = ticker + suffix
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yt}?interval=1d&range=60d"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        result = d.get("chart",{}).get("result",[])
        if not result: return None
        meta = result[0].get("meta",{})
        quotes = result[0].get("indicators",{}).get("quote",[{}])[0]

        closes_raw = quotes.get("close",[])
        highs_raw = quotes.get("high",[])
        lows_raw = quotes.get("low",[])
        vols_raw = quotes.get("volume",[])

        closes = [v for v in closes_raw if v is not None]
        highs = [v for v in highs_raw if v is not None]
        lows = [v for v in lows_raw if v is not None]
        vols = [v for v in vols_raw if v is not None]

        if len(closes) < 20: return None

        price = meta.get("regularMarketPrice") or closes[-1]
        prev = meta.get("previousClose") or meta.get("chartPreviousClose") or closes[-2]
        change = round(((price-prev)/prev)*100,2) if prev else 0

        volume = meta.get("regularMarketVolume") or (vols[-1] if vols else 0)
        avg_vol = sum(vols[-11:-1])/10 if len(vols)>=11 else (volume or 1)
        vol_ratio = round(volume/avg_vol,2) if avg_vol>0 else 1.0

        rsi = calc_rsi(closes)
        atr = calc_atr(highs, lows, closes)
        ma20 = calc_ma(closes, 20)
        ma50 = calc_ma(closes, 50)
        ma200 = calc_ma(closes, 200)

        atr_pct = round((atr/price)*100,2) if atr and price else None
        above_sma20 = price > ma20 if ma20 else None
        above_sma50 = price > ma50 if ma50 else None
        above_sma200 = price > ma200 if ma200 else None
        sma20_dist = round(((price-ma20)/ma20)*100,2) if ma20 else None

        score = 0
        if rsi:
            if 40<=rsi<=60: score+=25
            elif 35<=rsi<=65: score+=18
            elif 30<=rsi<=70: score+=10
        if vol_ratio>=2: score+=20
        elif vol_ratio>=1.5: score+=15
        elif vol_ratio>=1.2: score+=10
        elif vol_ratio>=1: score+=5
        if above_sma20 is True:
            score += 20 if sma20_dist and 0<=sma20_dist<=3 else 10
        if change > 0: score+=15
        if above_sma50 is True: score+=10
        if above_sma200 is True: score+=10

        currency = meta.get("currency","USD")
        price_str = f"{price:.2f} €" if currency=="EUR" else f"${price:.2f}"

        return {
            "ticker":ticker, "priceStr":price_str, "price":price,
            "change":change, "volRatio":vol_ratio, "rsi":rsi,
            "rsiSignal":rsi_signal(rsi), "atrPct":atr_pct,
            "aboveSMA20":above_sma20, "aboveSMA50":above_sma50, "aboveSMA200":above_sma200,
            "sma20Dist":sma20_dist, "macdBullish":None, "bbPct":None,
            "stochK":None, "adx":None, "momentum":None,
            "tvRecommendation":"N/A", "tvScore":None,
            "buySignals":None, "sellSignals":None, "neutralSignals":None,
            "preScore":min(100,score), "dataSource":"Yahoo Finance"
        }
    except Exception:
        return None

# ============================================================
# News
# ============================================================
def fetch_news(query, news_key):
    if not news_key: return []
    try:
        url = f"https://newsapi.org/v2/everything?q={urllib.parse.quote(query)}&sortBy=publishedAt&pageSize=3&apiKey={news_key}"
        req = urllib.request.Request(url, headers={"User-Agent":"TradeDashboard/3.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
            return [a["title"] for a in d.get("articles",[])[:3]]
    except Exception:
        return []

# ============================================================
# Groq KI
# ============================================================
def call_groq(prompt, groq_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = json.dumps({
        "model":"llama-3.3-70b-versatile",
        "messages":[{"role":"user","content":prompt}],
        "temperature":0.3,
        "max_tokens":1500
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type":"application/json",
        "Authorization":f"Bearer {groq_key}"
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"]

# ============================================================
# Main Handler
# ============================================================
class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length",0))
            body = json.loads(self.rfile.read(length).decode())
            result = self._handle(body)
            self._respond(200, result)
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, code, data):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")

    def _handle(self, body):
        groq_key = os.environ.get("GROQ_API_KEY")
        news_key = os.environ.get("NEWS_API_KEY")
        if not groq_key:
            raise Exception("GROQ_API_KEY fehlt")

        index = body.get("index","dax")
        date = body.get("date","heute")
        is_de = index in ["dax","mdax","sdax"]
        exchange = EXCHANGE_MAP[index]
        screener = SCREENER_MAP[index]
        suffix = YAHOO_SUFFIX[index]
        tickers = TICKERS.get(index, TICKERS["dax"])
        label = INDEX_LABELS[index]

        # Fetch data — TradingView first, Yahoo fallback per ticker
        results = []
        data_source = "Yahoo Finance"
        for ticker in tickers:
            data = None
            if TV_AVAILABLE:
                data = get_tv_data(ticker, exchange, screener)
            if data is None:
                data = get_yahoo_data(ticker, suffix, screener)
            if data:
                results.append(data)

        if results:
            tv_count = sum(1 for r in results if r.get("dataSource")=="TradingView")
            data_source = f"TradingView ({tv_count}) + Yahoo ({len(results)-tv_count})" if tv_count > 0 else "Yahoo Finance"

        if not results:
            raise Exception(f"Keine Marktdaten verfügbar für {label}. Bitte später erneut versuchen.")

        # Sort by pre-score, take top 15
        results.sort(key=lambda x: x["preScore"], reverse=True)
        top15 = results[:15]

        # News
        news_q = f"{label} Aktien Deutschland" if is_de else f"{label} stocks Wall Street"
        news = fetch_news(news_q, news_key)

        # Build prompt context
        lines = []
        for s in top15:
            tv_info = f"TV:{s['tvRecommendation']} ({s['buySignals']}↑/{s['sellSignals']}↓)" if s.get("tvRecommendation") != "N/A" else "TV:n/a"
            macd_info = f"MACD:{'bull' if s['macdBullish'] else 'bear'}" if s['macdBullish'] is not None else "MACD:n/a"
            adx_info = f"ADX:{s['adx']}" if s['adx'] else "ADX:n/a"
            lines.append(
                f"{s['ticker']}: {s['priceStr']} Δ{'+' if s['change']>0 else ''}{s['change']}% | "
                f"RSI:{s['rsi']}({s['rsiSignal']}) | Vol:{s['volRatio']}x | "
                f"ATR:{s['atrPct']}% | SMA20:{'+' if s.get('aboveSMA20') else ''}{s.get('sma20Dist','?')}% | "
                f"{tv_info} | {macd_info} | {adx_info} | Score:{s['preScore']}/100"
            )

        news_ctx = "\nNews:\n" + "\n".join(f"- {n}" for n in news) if news else ""
        einstieg = "09:15 Uhr" if is_de else "15:30 MEZ"

        prompt = f"""Du bist ein professioneller Intraday-Trader (20 Jahre Erfahrung).
Analysiere diese {label}-Aktien fuer Intraday-Long-Trades am {date}.
Datenquelle: {data_source}

KANDIDATEN (Top 15 nach Pre-Score):
{chr(10).join(lines)}
{news_ctx}

KRITERIEN (streng anwenden):
- RSI idealerweise 40-65 (nicht ueberkauft)
- Volumen-Ratio > 1.2
- Kurs ueber SMA20
- MACD bullish (falls verfuegbar)
- CRV: Stop = 1.0x ATR, Ziel = 2.0x ATR (mind. 1.5:1)
- TV STRONG_BUY oder BUY bevorzugen

TREFFERWAHRSCHEINLICHKEIT:
- TV-Signal + MACD + ADX: 35%
- RSI-Qualitaet: 25%
- Volumen-Anomalie: 20%
- Katalysator/Marktumfeld: 20%

Waehle die 3 BESTEN. Antworte NUR mit JSON-Array ohne Markdown:
[{{"ticker":"RHM","name":"Rheinmetall","preis":"1.570 EUR","wahrscheinlichkeit":76,
"einstieg":"{einstieg}","ziel":"+2.1%","stop":"-1.1%","crv":"1.9:1",
"katalysator":"TV BUY 18/26, RSI 54, Vol 2.3x, MACD bullish",
"risiko":"Gewinnmitnahmen","index":"{label}"}}]
Genau 3 Titel. wahrscheinlichkeit als Integer."""

        response = call_groq(prompt, groq_key)
        clean = response.replace("```json","").replace("```","").strip()
        start = clean.find("[")
        end = clean.rfind("]") + 1
        if start == -1 or end == 0:
            raise Exception(f"Kein JSON: {clean[:300]}")

        stocks = json.loads(clean[start:end])

        # Enrich with real data
        enriched = []
        for s in stocks:
            live = next((r for r in results if r["ticker"]==s["ticker"]), None)
            if live:
                s["preis"] = live["priceStr"]
                s["indikatoren"] = {
                    "rsi": live["rsi"], "rsiSignal": live["rsiSignal"],
                    "volRatio": live["volRatio"], "atrPct": live["atrPct"],
                    "aboveSMA20": live["aboveSMA20"], "aboveSMA50": live["aboveSMA50"],
                    "aboveSMA200": live["aboveSMA200"], "sma20Dist": live["sma20Dist"],
                    "macdBullish": live["macdBullish"], "bbPct": live["bbPct"],
                    "stochK": live["stochK"], "adx": live["adx"],
                    "momentum": live["momentum"], "tvRecommendation": live["tvRecommendation"],
                    "tvScore": live["tvScore"], "buySignals": live["buySignals"],
                    "sellSignals": live["sellSignals"], "neutralSignals": live["neutralSignals"],
                    "preScore": live["preScore"], "dataSource": live["dataSource"]
                }
            enriched.append(s)

        return {
            "stocks": enriched,
            "marketContext": {"idxName": label, "idxChange": None, "vix": None},
            "dataQuality": {
                "tickersAnalyzed": len(results),
                "tickersWithFullData": len(top15),
                "newsHeadlines": len(news),
                "dataSource": data_source,
                "tvAvailable": TV_AVAILABLE,
                "model": "Groq llama-3.3-70b",
                "timestamp": date
            }
        }

    def log_message(self, format, *args):
        pass
