# NFL Matchup Board

Weekly football-pool comparison board. One join per game: nflverse team form, injuries, depth charts and snap counts, PFF pressure, Next Gen Stats, nfelo (or the moneyline), and outdoor weather.

No paid odds API. Numbers are context, not predicted scores.

## Pages

- **Week board** — every game in one sortable grid: kickoff in Pacific, spread, home win probability, total, conditions, out/questionable counts, and the biggest statistical mismatch. Tick a row to open that game.
- **Game page** — hero card with both clubs, market and nfelo numbers, why the game stands out, availability, and side-by-side comparison bars grouped into passing, rushing, trenches, scoring and special teams. A second tab holds the full injury report.
- **Teams** — season-to-date form for all 32 clubs, ranked by nfelo, filterable by conference.
- **Injuries** — the whole week's report with status, team and starters-only filters.

Every column header and metric label carries a hover definition, and each page has a "What the numbers mean" glossary.

## Local

```bash
cd nfl-matchup-board
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Omarchy, Super+Space → **NFL Board** starts the local server and opens it as a web app (`scripts/nfl-board`).

## Streamlit Community Cloud (private family invite)

1. Push this repo to GitHub (private is fine).
2. https://share.streamlit.io → New app → this repo, `app.py`, Python 3.12+.
3. App settings → **Make app private** → invite family emails.
4. Cloud sleeps when idle; first open after sleep takes ~30s.

Data URLs are public nflverse / nfelo / Open-Meteo. No extra accounts.
