module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const groqKey = process.env.GROQ_API_KEY;
  const newsKey = process.env.NEWS_API_KEY;
  if (!groqKey) return res.status(500).json({ error: 'GROQ_API_KEY fehlt in Vercel Environment Variables' });

  const { market, index, date } = req.body;

  const TICKERS = {
    dax:    ['RHM.DE','MUV2.DE','CBK.DE','DBK.DE','SAP.DE','SIE.DE','BAS.DE','ALV.DE','BMW.DE','MBG.DE','VOW3.DE','ADS.DE','BEI.DE','HNR1.DE','MTX.DE'],
    mdax:   ['AIR.DE','BOSS.DE','COP.DE','DHER.DE','DWS.DE','ENR.DE','FRE.DE','HAG.DE','HLE.DE','HOT.DE','IFX.DE','KGX.DE','LEG.DE','NDA.DE','PSM.DE','SDF.DE','SHL.DE','SMHN.DE','TUI1.DE','VNA.DE'],
    sdax:   ['AAD.DE','AIXA.DE','BC8.DE','DIC.DE','DLG.DE','DWNI.DE','ECK.DE','EMH.DE','EVT.DE','FNTN.DE','GBF.DE','HAB.DE','HHFA.DE','INH.DE','KSB.DE','MLP.DE','NOEJ.DE','HOMG.DE','GYC.DE','GLJ.DE'],
    nasdaq: ['NVDA','AAPL','MSFT','META','GOOGL','AMZN','TSLA','AVGO','QCOM','AMD','NFLX','ADBE','CRM','CSCO','TXN','MU','PYPL','INTC','LRCX','KLAC'],
    dow:    ['JPM','GS','MS','BAC','WMT','HD','MCD','KO','PG','JNJ','UNH','V','AXP','IBM','CAT','BA','MMM','HON','CVX','XOM'],
    sp500:  ['LMT','RTX','NOC','GD','HII','F','GM','DIS','UBER','ABNB','SQ','SHOP','ZM','PLTR','COIN','RBLX','HOOD','RIVN','SNAP','NET']
  };

  const INDEX_LABELS = {
    dax:'DAX', mdax:'MDAX', sdax:'SDAX',
    nasdaq:'NASDAQ', dow:'Dow Jones', sp500:'S&P 500'
  };

  const isDE = ['dax','mdax','sdax'].includes(index);

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
      return { ticker, priceStr, change: parseFloat(change), volRatio: parseFloat(volRatio) };
    } catch { return null; }
  }

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

  try {
    const selectedTickers = TICKERS[index] || TICKERS['dax'];
    const priceResults = await Promise.all(selectedTickers.slice(0, 20).map(fetchPrice));
    const validPrices = priceResults.filter(Boolean);
    validPrices.sort((a, b) => b.volRatio - a.volRatio);

    const newsQuery = isDE ? `${INDEX_LABELS[index]} Aktien Deutschland` : `${INDEX_LABELS[index]} stocks Wall Street`;
    const news = await fetchNews(newsQuery);

    const priceContext = validPrices.map(p =>
      `${p.ticker.replace('.DE','')}: ${p.priceStr}, ${p.change > 0 ? '+' : ''}${p.change}%, Vol-Ratio ${p.volRatio}x`
    ).join('\n');

    const newsContext = news.length > 0
      ? `\nAktuelle News:\n${news.map(n => `- ${n}`).join('\n')}`
      : '';

    const prompt = `Du bist ein professioneller Intraday-Trader. Analysiere diese ${INDEX_LABELS[index]}-Aktien fuer Intraday-Long-Trades am ${date}.

LIVE-KURSDATEN:
${priceContext}
${newsContext}

KRITERIEN:
- Volumen-Ratio idealerweise > 1.0
- Positiver Tageschange ODER starker Katalysator
- CRV mindestens 1.5:1
- Trefferwahrscheinlichkeit = technisches Setup 30% + Volumen 25% + Katalysator 25% + Marktumfeld 20%

Waehle die 3 BESTEN Kandidaten.
Antworte NUR mit reinem JSON-Array ohne Markdown ohne Backticks ohne Text davor oder danach:
[{"ticker":"RHM","name":"Rheinmetall","preis":"1.570 EUR","wahrscheinlichkeit":74,"einstieg":"${isDE ? '09:15 Uhr' : '15:30 MEZ'}","ziel":"+1.8%","stop":"-1.0%","crv":"1.8:1","katalysator":"Vol 2.3x + Ruestungsbudgets","risiko":"Friedenssignale","index":"${INDEX_LABELS[index]}"}]
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
        temperature: 0.4,
        max_tokens: 1000
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
    if (!match) throw new Error(`Kein JSON: ${clean.substring(0, 200)}`);

    const stocks = JSON.parse(match[0]);

    const enriched = stocks.map(s => {
      const live = validPrices.find(p =>
        p.ticker === s.ticker ||
        p.ticker === s.ticker + '.DE' ||
        p.ticker.replace('.DE', '') === s.ticker
      );
      if (live) s.preis = live.priceStr;
      return s;
    });

    return res.status(200).json({
      stocks: enriched,
      dataQuality: {
        livePrices: validPrices.length,
        newsHeadlines: news.length,
        model: 'Groq llama-3.3-70b',
        timestamp: new Date().toISOString()
      }
    });

  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
