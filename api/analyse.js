const https = require('https');

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'GEMINI_API_KEY fehlt in Vercel Environment Variables' });

  const { market, date } = req.body;

  const prompts = {
    de: `Du bist ein erfahrener Intraday-Trader. Analysiere den deutschen Aktienmarkt (DAX) fuer Datum: ${date}. Gib die 3 aussichtsreichsten DAX-Einzelaktien fuer Intraday-Long-Trades an. Antworte NUR mit reinem JSON-Array ohne Markdown ohne Backticks ohne Text davor oder danach. Exakt dieses Format: [{"ticker":"RHM","name":"Rheinmetall","preis":"1.570 EUR","wahrscheinlichkeit":71,"einstieg":"09:15 Uhr","ziel":"+1.8%","stop":"-1.0%","crv":"1.8:1","katalysator":"Ruestungsbudgets steigen","risiko":"Friedenssignale"}] Genau 3 Titel.`,
    us: `Du bist ein erfahrener Intraday-Trader. Analysiere den US-Aktienmarkt (NYSE/NASDAQ) fuer Datum: ${date}. Gib die 3 aussichtsreichsten Einzelaktien fuer Intraday-Long-Trades ab 15:30 MEZ an. Antworte NUR mit reinem JSON-Array ohne Markdown ohne Backticks ohne Text davor oder danach. Exakt dieses Format: [{"ticker":"CVX","name":"Chevron","preis":"$162","wahrscheinlichkeit":68,"einstieg":"15:30 MEZ","ziel":"+2.1%","stop":"-1.2%","crv":"1.8:1","katalysator":"Oel ueber $100","risiko":"Oelpreisrueckgang"}] Genau 3 US-Titel.`
  };

  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`;

    const body = JSON.stringify({
      contents: [{ parts: [{ text: prompts[market] }] }],
      generationConfig: { temperature: 0.7, maxOutputTokens: 1000 }
    });

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Gemini Fehler ${response.status}: ${errText}`);
    }

    const data = await response.json();
    const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';
    const clean = text.replace(/```json|```/g, '').trim();
    const match = clean.match(/\[[\s\S]*\]/);
    if (!match) throw new Error(`Kein JSON gefunden. Antwort war: ${clean.substring(0, 200)}`);

    const stocks = JSON.parse(match[0]);
    return res.status(200).json({ stocks });

  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
