module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const groqKey = process.env.GROQ_API_KEY;
  const newsKey = process.env.NEWS_API_KEY;
  if (!groqKey) return res.status(500).json({ error: 'GROQ_API_KEY fehlt' });

  const { market, index, date } = req.body;

  // ============================================================
  // TICKER POOLS — maximale Abdeckung
  // ============================================================
  const TICKERS = {
    dax: [
      'RHM.DE','MUV2.DE','CBK.DE','DBK.DE','SAP.DE','SIE.DE','BAS.DE','ALV.DE',
      'BMW.DE','MBG.DE','VOW3.DE','ADS.DE','BEI.DE','HNR1.DE','MTX.DE','DTE.DE',
      'EOAN.DE','RWE.DE','HEI.DE','MRK.DE','SHL.DE','FRE.DE','AIR.DE','BNR.DE',
      'CON.DE','DTG.DE','ENR.DE','HAG.DE','HFG.DE','IFX.DE','LIN.DE','MAN.DE',
      'NDA.DE','QIA.DE','SRT3.DE','SY1.DE','VNA.DE','WDI.DE','ZAL.DE','1COV.DE'
    ],
    mdax: [
      'AIR.DE','BOSS.DE','COP.DE','DHER.DE','DWS.DE','ENR.DE','FRE.DE','HAG.DE',
      'HLE.DE','HOT.DE','IFX.DE','KGX.DE','LEG.DE','NDA.DE','PSM.DE','SDF.DE',
      'SHL.DE','SMHN.DE','TUI1.DE','VNA.DE','AAD.DE','AIXA.DE','BC8.DE','CLIQ.DE',
      'DIC.DE','DLG.DE','DWNI.DE','ECK.DE','EMH.DE','EVT.DE','FNTN.DE','GBF.DE',
      'GYC.DE','HAB.DE','HHFA.DE','INH.DE','KSB.DE','MLP.DE','NOEJ.DE','HOMG.DE',
      'GLJ.DE','EVK.DE','DEQ.DE','MOR.DE','NDX1.DE','NTCO.DE','PBB.DE','RRTL.DE',
      'WCH.DE','SFQ.DE'
    ],
    sdax: [
      'AAD.DE','AIXA.DE','ARND.DE','B5A.DE','BC8.DE','CLIQ.DE','DIC.DE','DLG.DE',
      'DNKA.DE','DWNI.DE','ECK.DE','EMH.DE','EVT.DE','FNTN.DE','GBF.DE','GYC.DE',
      'HAB.DE','HHFA.DE','HHX.DE','HOMG.DE','INH.DE','KSB.DE','MLP.DE','MWRK.DE',
      'NOEJ.DE','GLJ.DE','EVK.DE','DEQ.DE','MOR.DE','NDX1.DE','NTCO.DE','PBB.DE',
      'RRTL.DE','WCH.DE','SFQ.DE','ACX.DE','AOF.DE','BIO3.DE','DBAN.DE','ELGX.DE',
      'GBF.DE','JUVE.DE','KSB.DE','LBK.DE','MBB.DE','NGLOY.DE','OHB.DE','PAH3.DE',
      'SGCG.DE','TLX.DE'
    ],
    nasdaq: [
      'NVDA','AAPL','MSFT','META','GOOGL','AMZN','TSLA','AVGO','QCOM','AMD',
      'NFLX','ADBE','CRM','CSCO','TXN','MU','PYPL','INTC','LRCX','KLAC',
      'MRVL','AMAT','SNPS','CDNS','ASML','MCHP','ADI','NXPI','SWKS','QRVO',
      'MTCH','DOCU','ZM','CRWD','OKTA','DDOG','NET','SNOW','PLTR','COIN',
      'RBLX','HOOD','RIVN','LCID','SHOP','SQ','UBER','ABNB','DASH','LYFT'
    ],
    dow: [
      'JPM','GS','MS','BAC','WMT','HD','MCD','KO','PG','JNJ',
      'UNH','V','AXP','IBM','CAT','BA','MMM','HON','CVX','XOM',
      'AMGN','CRM','DIS','DOW','GE','MRK','NKE','RTX','TRV','VZ'
    ],
    sp500: [
      'LMT','RTX','NOC','GD','HII','F','GM','DIS','UBER','ABNB',
      'SQ','SHOP','ZM','PLTR','COIN','RBLX','HOOD','RIVN','SNAP','NET',
      'BABA','JD','PDD','NIO','XPEV','LI','DKNG','PENN','MGM','CZR',
      'DAL','UAL','AAL','CCL','RCL','NCLH','MAR','HLT','H','IHG',
      'ENPH','FSLR','RUN','SEDG','BE','PLUG','BLDP','FCEL','CHPT','EVGO'
    ]
  };

  const INDEX_LABELS = {
    dax:'DAX', mdax:'MDAX', sdax:'SDAX',
    nasdaq:'NASDAQ', dow:'Dow Jones', sp500:'S&P 500'
  };

  const isDE = ['dax','mdax','sdax'].includes(index);

  // ============================================================
  // RSI Berechnung aus Schlusskursen
  // ============================================================
  function calcRSI(closes, period = 14) {
    if (closes.length < period + 1) return null;
    let gains = 0, losses = 0;
    for (let i = closes.length - period; i < closes.length; i++) {
      const diff = closes[i] - closes[i - 1];
      if (diff > 0) gains += diff;
      else losses += Math.abs(diff);
    }
    const avgGain = gains / period;
    const avgLoss = losses / period;
    if (avgLoss === 0) return 100;
    const rs = avgGain / avgLoss;
    return Math.round(100 - (100 / (1 + rs)));
  }

  // ============================================================
  // ATR Berechnung (Average True Range)
  // ============================================================
  function calcATR(highs, lows, closes, period = 14) {
    if (highs.length < period + 1) return null;
    const trs = [];
    for (let i = 1; i < highs.length; i++) {
      const tr = Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      );
      trs.push(tr);
    }
    const recentTRs = trs.slice(-period);
    return recentTRs.reduce((a, b) => a + b, 0) / recentTRs.length;
  }

  // ============================================================
  // Moving Average
  // ============================================================
  function calcMA(closes, period) {
    if (closes.length < period) return null;
    const slice = closes.slice(-period);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  }

  // ============================================================
  // Yahoo Finance — Live Kursdaten + Indikatoren
  // ============================================================
  async function fetchFullData(ticker) {
    try {
      // Fetch 60 days for reliable indicator calculation
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1d&range=60d`;
      const r = await fetch(url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; TradeDashboard/1.0)' }
      });
      if (!r.ok) return null;
      const d = await r.json();
      const result = d?.chart?.result?.[0];
      if (!result) return null;

      const meta = result.meta;
      const quotes = result.indicators?.quote?.[0];
      const timestamps = result.timestamp;

      if (!meta || !quotes || !timestamps) return null;

      const closes = quotes.close.filter(v => v !== null && v !== undefined);
      const highs = quotes.high.filter(v => v !== null && v !== undefined);
      const lows = quotes.low.filter(v => v !== null && v !== undefined);
      const volumes = quotes.volume.filter(v => v !== null && v !== undefined);

      if (closes.length < 20) return null;

      const price = meta.regularMarketPrice;
      const prevClose = meta.previousClose || meta.chartPreviousClose || closes[closes.length - 2];
      const change = prevClose ? (((price - prevClose) / prevClose) * 100) : 0;

      const volume = meta.regularMarketVolume || volumes[volumes.length - 1] || 0;
      const avgVol10 = volumes.slice(-11, -1).reduce((a, b) => a + b, 0) / 10;
      const volRatio = avgVol10 > 0 ? volume / avgVol10 : 1;

      // Technical indicators
      const rsi = calcRSI(closes);
      const atr = calcATR(highs, lows, closes);
      const ma20 = calcMA(closes, 20);
      const ma50 = calcMA(closes, 50);

      const atrPct = atr && price ? ((atr / price) * 100) : null;
      const aboveMA20 = ma20 ? price > ma20 : null;
      const aboveMA50 = ma50 ? price > ma50 : null;
      const ma20Dist = ma20 ? (((price - ma20) / ma20) * 100) : null;

      const currency = meta.currency || 'USD';
      const priceStr = currency === 'EUR'
        ? `${price.toFixed(2)} €`
        : `$${price.toFixed(2)}`;

      // RSI signal
      let rsiSignal = 'neutral';
      if (rsi !== null) {
        if (rsi < 30) rsiSignal = 'ueberverkauft';
        else if (rsi < 40) rsiSignal = 'schwach';
        else if (rsi > 70) rsiSignal = 'ueberkauft';
        else if (rsi > 60) rsiSignal = 'stark';
        else rsiSignal = 'neutral';
      }

      return {
        ticker,
        priceStr,
        price,
        change: parseFloat(change.toFixed(2)),
        volRatio: parseFloat(volRatio.toFixed(2)),
        volume: Math.round(volume),
        rsi,
        rsiSignal,
        atrPct: atrPct ? parseFloat(atrPct.toFixed(2)) : null,
        aboveMA20,
        aboveMA50,
        ma20Dist: ma20Dist ? parseFloat(ma20Dist.toFixed(2)) : null,
        currency
      };
    } catch { return null; }
  }

  // ============================================================
  // Marktumfeld — VIX + Index-Trend
  // ============================================================
  async function fetchMarketContext() {
    try {
      const vixTicker = isDE ? '%5EVDAX-NEW.DE' : '%5EVIX';
      const idxTicker = isDE ? '%5EGDAXI' : '%5EGSPC';

      const [vixRes, idxRes] = await Promise.all([
        fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${vixTicker}?interval=1d&range=5d`, {
          headers: { 'User-Agent': 'Mozilla/5.0' }
        }),
        fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${idxTicker}?interval=1d&range=5d`, {
          headers: { 'User-Agent': 'Mozilla/5.0' }
        })
      ]);

      let vix = null, idxChange = null, idxName = isDE ? 'DAX' : 'S&P 500';

      if (vixRes.ok) {
        const vd = await vixRes.json();
        vix = vd?.chart?.result?.[0]?.meta?.regularMarketPrice;
      }

      if (idxRes.ok) {
        const id = await idxRes.json();
        const meta = id?.chart?.result?.[0]?.meta;
        if (meta) {
          const prev = meta.previousClose || meta.chartPreviousClose;
          const curr = meta.regularMarketPrice;
          if (prev && curr) idxChange = parseFloat((((curr - prev) / prev) * 100).toFixed(2));
        }
      }

      return { vix: vix ? parseFloat(vix.toFixed(1)) : null, idxChange, idxName };
    } catch { return { vix: null, idxChange: null, idxName: isDE ? 'DAX' : 'S&P 500' }; }
  }

  // ============================================================
  // News
  // ============================================================
  async function fetchNews(query) {
    if (!newsKey) return [];
    try {
      const url = `https://newsapi.org/v2/everything?q=${encodeURIComponent(query)}&sortBy=publishedAt&pageSize=3&apiKey=${newsKey}`;
      const r = await fetch(url);
      if (!r.ok) return [];
      const d = await r.json();
      return (d.articles || []).map(a => a.title).slice(0, 3);
    } catch { return []; }
  }

  // ============================================================
  // Score-Berechnung (transparent, vor KI-Analyse)
  // ============================================================
  function calcPreScore(stock) {
    let score = 0;

    // RSI (0-25 Punkte)
    if (stock.rsi !== null) {
      if (stock.rsi >= 40 && stock.rsi <= 60) score += 25; // ideal
      else if (stock.rsi >= 35 && stock.rsi <= 65) score += 18;
      else if (stock.rsi >= 30 && stock.rsi <= 70) score += 10;
      else score += 0; // überkauft/überverkauft
    }

    // Volumen-Ratio (0-25 Punkte)
    if (stock.volRatio >= 2.0) score += 25;
    else if (stock.volRatio >= 1.5) score += 20;
    else if (stock.volRatio >= 1.2) score += 15;
    else if (stock.volRatio >= 1.0) score += 10;
    else score += 0;

    // Tagesveränderung (0-25 Punkte)
    if (stock.change >= 1.5) score += 25;
    else if (stock.change >= 0.5) score += 20;
    else if (stock.change >= 0) score += 12;
    else if (stock.change >= -0.5) score += 5;
    else score += 0;

    // MA20 (0-25 Punkte)
    if (stock.aboveMA20 === true) {
      if (stock.ma20Dist >= 0 && stock.ma20Dist <= 3) score += 25; // knapp über MA20 ideal
      else if (stock.ma20Dist > 3 && stock.ma20Dist <= 6) score += 15;
      else score += 8;
    } else {
      score += 0;
    }

    return Math.min(100, score);
  }

  try {
    const selectedTickers = TICKERS[index] || TICKERS['dax'];

    // Fetch all data in parallel
    const [priceResults, marketCtx, news] = await Promise.all([
      Promise.all(selectedTickers.map(fetchFullData)),
      fetchMarketContext(),
      fetchNews(isDE ? `${INDEX_LABELS[index]} Aktien Deutschland Boerse` : `${INDEX_LABELS[index]} stocks Wall Street`)
    ]);

    const validStocks = priceResults
      .filter(Boolean)
      .filter(s => s.rsi !== null); // nur Aktien mit vollständigen Daten

    // Pre-Score berechnen und sortieren
    const scoredStocks = validStocks
      .map(s => ({ ...s, preScore: calcPreScore(s) }))
      .sort((a, b) => b.preScore - a.preScore)
      .slice(0, 15); // Top 15 an KI übergeben

    // Marktfilter-Warnung
    const vixWarning = marketCtx.vix && marketCtx.vix > 25
      ? `⚠️ VDAX/VIX bei ${marketCtx.vix} — erhöhte Volatilität, nur konservative Einstiege!`
      : `✅ VDAX/VIX bei ${marketCtx.vix || 'unbekannt'} — normales Marktumfeld`;

    const idxWarning = marketCtx.idxChange !== null
      ? `${marketCtx.idxName} heute ${marketCtx.idxChange > 0 ? '+' : ''}${marketCtx.idxChange}% — ${marketCtx.idxChange > 0 ? 'positives Umfeld' : 'vorsichtig sein'}`
      : '';

    // Kontext für KI
    const stockContext = scoredStocks.map(s =>
      `${s.ticker.replace('.DE','')}: Kurs ${s.priceStr} | Δ ${s.change > 0 ? '+' : ''}${s.change}% | Vol-Ratio ${s.volRatio}x | RSI ${s.rsi} (${s.rsiSignal}) | ATR ${s.atrPct ? s.atrPct + '%' : 'n/a'} | MA20 ${s.aboveMA20 ? '+' + s.ma20Dist + '% darüber' : s.ma20Dist + '% darunter'} | Pre-Score ${s.preScore}/100`
    ).join('\n');

    const newsContext = news.length > 0
      ? `\nAktuelle News:\n${news.map(n => `- ${n}`).join('\n')}`
      : '';

    const prompt = `Du bist ein professioneller Intraday-Trader mit 20 Jahren Erfahrung. Analysiere die folgenden vorgefilterten ${INDEX_LABELS[index]}-Aktien fuer Intraday-Long-Trades am ${date}.

MARKTUMFELD:
${vixWarning}
${idxWarning}

VORAUSGEFILTERTE TOP-KANDIDATEN (bereits nach technischem Pre-Score sortiert):
${stockContext}
${newsContext}

DEINE AUFGABE:
Waehle die 3 BESTEN Intraday-Long-Kandidaten. Beruecksichtige:
1. RSI idealerweise zwischen 40-60 (nicht ueberkauft)
2. Volumen-Ratio > 1.2 (Handelsinteresse vorhanden)
3. Kurs ueber MA20 (Aufwaertstrend)
4. ATR fuer realistische Stop-Loss und Kursziel-Berechnung
5. Positiver Tageschange als Momentum-Bestaetigung
6. Sektor-Katalysator oder News als Ausloeser
7. Kein ueberkauftes RSI > 70

TREFFERWAHRSCHEINLICHKEIT berechnen als:
- RSI-Signal: 25%
- Volumen-Anomalie: 25%
- Trend (MA20/MA50): 25%
- Katalysator + Marktumfeld: 25%

Antworte NUR mit reinem JSON-Array ohne Markdown ohne Backticks:
[{
  "ticker": "RHM",
  "name": "Rheinmetall",
  "preis": "1.570 EUR",
  "wahrscheinlichkeit": 74,
  "einstieg": "${isDE ? '09:15 Uhr' : '15:30 MEZ'}",
  "ziel": "+1.8%",
  "stop": "-1.0%",
  "crv": "1.8:1",
  "katalysator": "Vol 2.3x + RSI 52 neutral + Ruestungsbudgets",
  "risiko": "Gewinnmitnahmen",
  "index": "${INDEX_LABELS[index]}",
  "indikatoren": {
    "rsi": 52,
    "rsiSignal": "neutral",
    "volRatio": 2.3,
    "atrPct": 1.8,
    "aboveMA20": true,
    "ma20Dist": 1.2,
    "preScore": 87,
    "vix": ${marketCtx.vix || 'null'},
    "idxChange": ${marketCtx.idxChange || 'null'}
  }
}]
Genau 3 Titel. wahrscheinlichkeit als Integer.`;

    const groqRes = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${groqKey}`
      },
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
        max_tokens: 1500
      })
    });

    if (!groqRes.ok) {
      const errText = await groqRes.text();
      throw new Error(`Groq Fehler ${groqRes.status}: ${errText}`);
    }

    const groqData = await groqRes.json();
    const text = groqData?.choices?.[0]?.message?.content || '';
    const clean = text.replace(/```json|```/g, '').trim();
    const match = clean.match(/\[[\s\S]*\]/);
    if (!match) throw new Error(`Kein JSON: ${clean.substring(0, 300)}`);

    const stocks = JSON.parse(match[0]);

    // Live-Kurse einsetzen + Indikatoren aus echten Daten anreichern
    const enriched = stocks.map(s => {
      const live = scoredStocks.find(p =>
        p.ticker === s.ticker ||
        p.ticker === s.ticker + '.DE' ||
        p.ticker.replace('.DE', '') === s.ticker
      );
      if (live) {
        s.preis = live.priceStr;
        // Echte Indikatoren überschreiben KI-Schätzung
        s.indikatoren = {
          rsi: live.rsi,
          rsiSignal: live.rsiSignal,
          volRatio: live.volRatio,
          atrPct: live.atrPct,
          aboveMA20: live.aboveMA20,
          aboveMA50: live.aboveMA50,
          ma20Dist: live.ma20Dist,
          preScore: live.preScore,
          vix: marketCtx.vix,
          idxChange: marketCtx.idxChange,
          idxName: marketCtx.idxName
        };
      }
      return s;
    });

    return res.status(200).json({
      stocks: enriched,
      marketContext: marketCtx,
      dataQuality: {
        tickersAnalyzed: validStocks.length,
        tickersWithFullData: scoredStocks.length,
        newsHeadlines: news.length,
        model: 'Groq llama-3.3-70b',
        timestamp: new Date().toISOString()
      }
    });

  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
