export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'GEMINI_API_KEY fehlt in Vercel Environment Variables' });

  const { market, date } = req.body;

  const prompts = {
    de: `Du bist ein erfahrener Intraday-Trader. Analysiere heute den deutschen Aktienmarkt (DAX). Datum: ${date}.
Gib die 3 aussichtsreichsten DAX-Einzelaktien für Intraday-Long-Trades an.
Antworte NUR mit einem reinen JSON-Array. Kein Markdown, keine Backticks, kein Text davor oder danach.
Format exakt so:
[{"ticker":"RHM","name":"Rheinmetall","preis":"1.570 €","wahrscheinlichkeit":71,"einstieg":"09:15 Uhr","ziel":"+1.8%","stop":"-1.0%","crv":"1.8:1","katalysator":"Iran-Krieg treibt Rüstungsbudgets","risiko":"Friedenssignale"}]
Genau 3 Titel. Wahrscheinlichkeit als Zahl zwischen 0 und 100.`,

    us: `Du bist ein erfahrener Intraday-Trader. Analysiere heute den US-Aktienmarkt (NYSE/NASDAQ). Datum: ${date}.
Gib die 3 aussichtsreichsten Einzelaktien für Intraday-Long-Trades ab 15:30 MEZ an.
Antworte NUR mit einem reinen JSON-Array. Kein Markdown, keine Backticks, kein Text davor oder danach.
Format exakt so:
[{"ticker":"CVX","name":"Chevron","preis":"$162","wahrscheinlichkeit":68,"einstieg":"15:30 MEZ","ziel":"+2.1%","stop":"-1.2%","crv":"1.8:1","katalysator":"Öl über $100","risiko":"Ölpreisrückgang"}]
Genau 3 US-Titel. Wahrscheinlichkeit als Zahl zwischen 0 und 100.`
  };

  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{
          parts: [{ text: prompts[market] }]
        }],
        generationConfig: {
          temperature: 0.7,
          maxOutputTokens: 1000,
        }
      })
    });

    if (!response.ok) {
      const err = await response.text();
      throw new Error(`Gemini API Fehler ${response.status}: ${err}`);
    }

    const data = await response.json();
    const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';

    // Clean response - remove any markdown if present
    const clean = text.replace(/```json|```/g, '').trim();
    const match = clean.match(/\[[\s\S]*\]/);
    if (!match) throw new Error('Kein gültiges JSON in der Antwort');

    const stocks = JSON.parse(match[0]);
    if (!Array.isArray(stocks) || stocks.length === 0) throw new Error('Leeres Ergebnis');

    return res.status(200).json({ stocks });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
