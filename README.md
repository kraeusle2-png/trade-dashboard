# 📊 Trade Dashboard — Gemini Edition (kostenlos)

## Schritt 1 — Gemini API Key holen (kostenlos)
1. aistudio.google.com aufrufen
2. Mit Google-Konto einloggen
3. Oben "Get API Key" → "Create API Key"
4. Key kopieren (AIza...)

## Schritt 2 — GitHub Repository
1. github.com → "New repository"
2. Name: `trade-dashboard`
3. Private → "Create repository"
4. Alle Dateien aus diesem ZIP hochladen:
   ```
   api/analyse.js
   public/index.html
   vercel.json
   ```
   WICHTIG: Direkt ins Root, nicht in Unterordner!

## Schritt 3 — Vercel Deploy
1. vercel.com → "Add New Project"
2. GitHub Repo `trade-dashboard` auswählen
3. Framework Preset: "Other"
4. Root Directory: . (Punkt lassen)
5. "Deploy" klicken

## Schritt 4 — API Key eintragen
1. Vercel → Projekt → Settings → Environment Variables
2. Neue Variable:
   Name:  GEMINI_API_KEY
   Value: AIza... (dein Key)
   Environments: Production + Preview + Development
3. Save → Deployments → Redeploy

## Schritt 5 — Als iPhone App
Safari → deine-url.vercel.app → Teilen ↑ → "Zum Home-Bildschirm"

## Kosten
- GitHub: KOSTENLOS
- Vercel: KOSTENLOS
- Gemini API: KOSTENLOS (1500 Anfragen/Tag)

⚠️ Keine Anlageberatung. Immer Stop-Loss setzen.
