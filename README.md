# India Swing Dashboard (NIFTY 50, top 30)

Daily swing-trade screener for 30 large NIFTY 50 stocks. A GitHub Action runs at **07:00 IST** on the
previous close, writes JSON, and publishes a static dashboard to GitHub Pages.

```
config.yaml        stocks, sector indices, thresholds, risk, gating (edit here)
src/               data, indicators, setups, regime, score, build
site/              index.html + app.js + style.css (reads site/data/*.json)
.github/workflows  daily.yml (cron + deploy)
```

## Publish (new repository)
Push the **contents of this folder** as the root of a new repo (the `.github` folder must sit at the repo root).
1. Create a new public repo, e.g. `india-swing`, and upload everything in this folder
   (include the hidden `.github` folder; do not upload `.venv`).
2. Settings > Pages > Source: **GitHub Actions**.
3. Actions > "India daily scan and deploy" > **Run workflow**.
4. Open `https://<you>.github.io/<repo>/`.

## Run locally (needs access to Yahoo Finance)
```cmd
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python -m pytest -q
python -m src.build
python -m http.server 8000 -d site
```

## Things to check after the first run
- **Banner warnings** list any Yahoo symbol that returned no data. A missing sector index skips the sector rule
  for its stocks instead of blocking them.
- **Index symbols** (`^CNXIT`, `^CNXAUTO`, `^CNXINFRA`, `^CNXCONSUM`, ...) are the Yahoo tickers I expect; edit
  `config.yaml` if one is wrong.
- **Constituents change.** Review the stock list against NSE's current NIFTY 50 and adjust `config.yaml`.
- **Thresholds are starting points:** breakout ATR 1.5%, shock -5%, India VIX block at 22.
- Earnings data for NSE stocks on Yahoo can be sparse, so earnings flags may be missing.
- GitHub pauses scheduled workflows after about 60 days without repository activity; re-run manually to resume.
- Signals use end-of-day bars; trade the next session. Not financial advice.
