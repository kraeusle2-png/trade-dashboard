module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const geminiKey = process.env.GEMINI_API_KEY;
  const newsKey = process.env.NEWS_API_KEY;
  if (!geminiKey) return res.status(500).json({ error: 'GEMINI_API_KEY fehlt' });

  const { market, index, date } = req.body;

  // All tickers by index
  const TICKERS = {
    // German indices
    dax:  ['RHM.DE','MUV2.DE','CBK.DE','DBK.DE','SAP.DE','SIE.DE','BAS.DE','ALV.DE','BMW.DE','MBG.DE','VOW3.DE','ADS.DE','BEI.DE','HNR1.DE','MTX.DE'],
    mdax: ['AIR.DE','EVK.DE','BOSS.DE','COP.DE','DEQ.DE','DHER.DE','DWS.DE','ENR.DE','FRE.DE','GXI.DE','HAG.DE','HLE.DE','HOT.DE','IFX.DE','KGX.DE','LEG.DE','MOR.DE','NDX1.DE','NDA.DE','NTCO.DE','PBB.DE','PSM.DE','RRTL.DE','SDF.DE','SHL.DE','SMHN.DE','SY1.DE','TUI1.DE','VNA.DE','WCH.DE'],
    sdax: ['AAD.DE','AIXA.DE','ARND.DE','B5A.DE','BC8.DE','CLIQ.DE','DIC.DE','DLG.DE','DNKA.DE','DWNI.DE','ECK.DE','ELGX.DE','EMH.DE','EVT.DE','FNTN.DE','GBF.DE','GKSC.DE','GLJ.DE','GYC.DE','HAB.DE','HHFA.DE','HHX.DE','HOMG.DE','INH.DE','JUVE.DE','KSB.DE','MLP.DE','MWRK.DE','NOEJ.DE','NGLOY.DE'],
    // US indices
    nasdaq: ['NVDA','AAPL','MSFT','META','GOOGL','AMZN','TSLA','AVGO','QCOM','INTC','AMD','NFLX','PYPL','ADBE','CRM','CSCO','TXN','MU','LRCX','KLAC'],
    dow:    ['JPM','GS','MS','BAC','WMT','HD','MCD','KO','PG','JNJ','UNH','V','AXP','IBM','CAT','BA','MMM','HON','CVX','XOM'],
    sp500:  ['LMT','RTX','NOC','GD','HII','F','GM','DIS','UBER','ABNB','SQ','SNAP','SHOP','ZM','PLTR','COIN','RBLX','HOOD','RIVN','LCID']
  };

  // Fetch live price from Yahoo Finance
  async function fetchPrice(ticker) {
    try {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?interval=1d&range=5d`;
      const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
      if (!r.ok) return null;
      const d = await r.json();
      const meta = d?.chart?.result?.[0]?.meta;
      if (!meta || !meta.regularMarketPrice) return null;
      const price = meta.regularMarketPrice;
      const prevClose = meta.previousClose || meta.chartPreviousClose;
      const change = prevClose ? (((price - prevClose) / prevClose) * 100).toFixed(2) : '0.00';
      const volume = meta.regularMarketVolume || 0;
      const avgVolume = meta.averageDailyVolume10Day || meta.averageDailyVolume3Month || volume;
      const volRatio = avgVolume > 0 ? (volume / avgVolume).toFixed(2) : '1.00';
      const currency = meta.currency || 'USD';
      const priceStr = currency === 'EUR' ? `${price.toFixed(2)} €` : `$${price.toFixed(2)}`;
      return { ticker, priceStr, change: parseFloat(change), volRatio: parseFloat(volRatio), raw: price };
    } catch { return null; }
  }

  // Fetch news
  async function fetchNews(query) {
    if (!newsKey) return [];
    try {
      const url = `https://newsapi.org/v2/everything?q=${encodeURIComponent(query)}&language=de&sortBy=publishedAt&pageSize=3&apiKey=${newsKey}`;
      const r = await fetch(url);
      if (!r.ok) return [];
      const d = await r.json();
      return (d.articles || []).map(a => a.title).slice(0, 3);
    } catch { return []; }
  }

  // Index label mapping
  const INDEX_LABELS = {
    dax: 'DAX', mdax: 'MDAX', sdax: 'SDAX',
    nasdaq: 'NASDAQ', dow: 'Dow Jones', sp500: 'S&P 500 / Sonstige'
  };

  const isDE = ['dax','mdax','sdax'].includes(index);
  const newsQuery = isDE
    ? `${INDEX_LABELS[index]} Aktien Deutschland Börse`
    : `${INDEX_LABELS[index]} stocks Wall Street NYSE`;

  try {
    const selectedTickers = TICKERS[index] || TICKERS['dax'];

    // Fetch prices in parallel (batch of max 20)
    const priceResults = await Promise.all(selectedTickers.slice(0, 20).map(fetchPrice));
    const validPrices = priceResults.filter(Boolean);

    // Sort by volume ratio descending (highest interest first)
    validPrices.sort((a, b) => b.volRatio - a.volRatio);

    // Fetch news
    const news = await fetchNews(newsQuery);

    // Build context
    const priceContext = validPrices.map(p =>
      `${p.ticker.replace('.DE','')}: Kurs ${p.priceStr}, Δ ${p.change>0?'+':''}${p.change}%, Vol-Ratio ${p.volRatio}x`
    ).join('\n');

    const newsContext = news.length > 0
      ? `\nAktuelle Schlagzeilen:\n${news.map(n => `- ${n}`).join('\n')}`
      : '';

    const prompt = `Du bist ein professioneller Intraday-Trader mit 20 Jahren Erfahrung. Analysiere die folgenden ${INDEX_LABELS[index]}-Aktien für Intraday-Long-Trades ${isDE ? 'heute' : 'ab 15:30 MEZ'} (${date}).

LIVE-MARKTDATEN:
${priceContext}
${newsContext}

AUSWAHLKRITERIEN (streng anwenden):
1. Volumen-Ratio idealerweise > 1.0 (erhöhtes Handelsinteresse)
2. Positiver Tageschange ODER klarer Katalysator
3. Realistisches CRV mindestens 1.5:1
4. Klarer Auslöser vorhanden (News, Sektorrotation, technisches Setup)
5. Kein unmittelbares Earnings-Risiko heute

TREFFERWAHRSCHEINLICHKEIT berechnen als gewichteter Score:
- Technisches Setup: 30%
- Volumen-Anomalie: 25%
- Katalysator-Stärke: 25%
- Gesamtmarktumfeld: 20%

Wähle die 3 BESTEN Kandidaten aus den obigen Daten.
Antworte NUR mit reinem JSON-Array ohne Markdown ohne Backticks:
[{"ticker":"RHM","name":"Rheinmetall","preis":"1.570 €","wahrscheinlichkeit":74,"einstieg":"${isDE?'09:15 Uhr':'15:30 MEZ'}","ziel":"+1.8%","stop":"-1.0%","crv":"1.8:1","katalysator":"Vol 2.3x + Rüstungsbudgets steigen","risiko":"Gewinnmitnahmen","index":"${INDEX_LABELS[index]}"}]
Genau 3 Titel. wahrscheinlichkeit als Integer.`;

    const geminiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${geminiKey}`;
    const geminiRes = await fetch(geminiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.4, maxOutputTokens: 1000 }
      })
    });

    if (!geminiRes.ok) {
      const errText = await geminiRes.text();
      throw new Error(`Gemini Fehler ${geminiRes.status}: ${errText}`);
    }

    const geminiData = await geminiRes.json();
    const text = geminiData?.candidates?.[0]?.content?.parts?.[0]?.text || '';
    const clean = text.replace(/```json|```/g, '').trim();
    const match = clean.match(/\[[\s\S]*\]/);
    if (!match) throw new Error(`Kein JSON: ${clean.substring(0, 200)}`);

    const stocks = JSON.parse(match[0]);

    // Enrich with live prices
    const enriched = stocks.map(s => {
      const live = validPrices.find(p =>
        p.ticker === s.ticker ||
        p.ticker === s.ticker + '.DE' ||
        p.ticker.replace('.DE','') === s.ticker
      );
      if (live) s.preis = live.priceStr;
      return s;
    });

    return res.status(200).json({
      stocks: enriched,
      dataQuality: {
        livePrices: validPrices.length,
        newsHeadlines: news.length,
        index: INDEX_LABELS[index],
        timestamp: new Date().toISOString()
      }
    });

  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
