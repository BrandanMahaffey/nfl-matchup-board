# Hafstats

Weekly football-pool comparison board. One join per game: nflverse team form, injuries, last-week snaps, OL/DL depth, PFR pressure, NGS, nfelo (or moneyline), and outdoor weather.

No PFF. No paid odds API. Numbers are context, not predicted scores.

## Local

```bash
cd nfl-matchup-board
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Omarchy, Super+Space → **Hafstats** starts the local server and opens it as a web app (`scripts/hafstats`).

## Streamlit Community Cloud (private family invite)

1. Push this repo to GitHub (private is fine).
2. https://share.streamlit.io → New app → this repo, `app.py`, Python 3.12+.
3. App settings → **Make app private** → invite family emails.
4. Cloud sleeps when idle; first open after sleep takes ~30s.

Data URLs are public nflverse / nfelo / Open-Meteo. No extra accounts.
