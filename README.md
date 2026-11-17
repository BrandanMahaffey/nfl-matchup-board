# NFL Matchup Board

Weekly football-pool comparison board. It puts one join per game in front of you: nflverse team form, injuries, depth charts and snap counts, PFR pressure, Next Gen Stats, nfelo (or the moneyline), and outdoor weather. Numbers are context, not predicted scores, and there is no paid odds API.

## Pages and game details

The hub has seven tabs:

- **Matchups** — phone and tablet widths (up to 820px) use responsive cards with kickoff, scores, odds, conditions, adjusted net, and a **View breakdown** link. Wider screens retain the sortable grid and row selection. Game links preserve season, week, and theme. Missing scores are labeled “Not available,” not inferred as final or live.
- **Power ratings** — latest published current nfelo snapshot and comparisons (source weeks can vary by team; not strict historical/pregame ratings).
- **Team stats** — season-to-date team form and league comparisons.
- **Adjusted EPA** — opponent-adjusted offense, defense, and net views, with a Special teams subview. The phone view uses a near-square plot area so identical X/Y EPA ranges retain comparable visual scale.
- **nflverse** — nflverse team aggregate tables.
- **Next Gen** — Next Gen Stats team aggregate views.
- **Injury report** — cumulative state through the selected week with status, team, and starters-only filters. Current weekly designations replace or clear prior weekly states; unresolved IR, PUP, NFI, and suspension states carry forward from their latest source report.

The **game detail** view has a matchup hero (clubs, market and nfelo numbers), the reason the game stands out, availability, and side-by-side bars for passing, rushing, trenches, scoring, and special teams. Its compact phone layout keeps game-detail metrics and panels readable without removing any values. The **Injuries** section contains the full game injury report. The game detail view includes the metric glossary.

On phones, injuries also appear as compact cards containing team, player, position, status, starter state, injury, practice, first status week, latest source week, and (in game detail) game information; the desktop full tables remain unchanged. No rows or fields are discarded at any width. Reference tables and the glossary retain all content in contained internal scrolling regions. Theme/Season/Week controls and section tabs use touch-friendly targets, Adjusted EPA uses a proportional phone-specific plot height, other charts resize responsively, and wider screens retain the sortable grid. Source links are tucked under **Sources**, and desktop grid instructions are omitted on smaller screens. Mobile cards follow schedule order; use the desktop grid for column sorting.

## Local setup

Python 3.14 is the supported runtime. From PowerShell:

```powershell
cd nfl-matchup-board
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

From Unix (including Omarchy):

```bash
cd nfl-matchup-board
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On **Windows**, double-click **NFL Board** on the Desktop (or Start Menu). It starts the local server if needed and opens the board in your browser. The installer is:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/install-windows-app.ps1
```

On **Omarchy**, Super+Space → **NFL Board** starts the local server and opens it as a web app (`scripts/nfl-board`).

There is no static build: this is a Streamlit WebSocket server. For a production-like local check, run `python -m compileall -q app.py data tests`, `python -m unittest discover -s tests -v`, and `python -m pip check`, then start the headless server:

```bash
python -m streamlit run app.py --server.headless true
```

`NFL_BOARD_PORT` is an optional local-launcher port override. For a server command, use Streamlit's `--server.port` and `--server.address` options (or `STREAMLIT_SERVER_PORT` and `STREAMLIT_SERVER_ADDRESS`).

## Streamlit Community Cloud

This is a Streamlit server application with server-side data fetches and WebSockets; static hosting and SPA fallback configuration are not supported.

Deployment requires GitHub access to the repository and a Streamlit Community Cloud account. Commit and push the complete application—not only `app.py`—including `data/`, `assets/`, `requirements.txt`, `runtime.txt`, and `.streamlit/config.toml`.

1. Push the reviewed repository to GitHub: `BrandanMahaffey/nfl-matchup-board`, branch `main`.
2. In Community Cloud, choose **New app**, that repository/branch, and entrypoint `app.py`.
3. In **Advanced settings**, select **Python 3.14**. `runtime.txt` remains runtime metadata for local or other hosted use; it does not select the Community Cloud interpreter. If Python 3.14 is unavailable in the selector, choose a supported version offered by the platform, run the local production check with it, and redeploy after selecting the final version.
4. No secrets or API keys are required. Current providers are public feeds fetched by the server; browsers receive no provider credentials. Future credentials belong in Cloud Secrets as `st.secrets`; locally use ignored `.streamlit/secrets.toml`. Never put secrets in client code or URLs.
5. Choose public or private sharing deliberately. For a private app, configure allowed viewers/invites in sharing settings.
6. Share the resulting `streamlit.app` URL. Existing query parameters such as `?season=2025&week=10&game=...` can be shared as deep links.

Cloud can sleep and cold-start time is variable, and public feeds can be unavailable, rate-limited, or change schema. Do not promise a fixed wake-up time.

## Data, coverage, and operational limits

- Public feeds can be slow, unavailable, rate-limited, or change schema. The source-fetch layer and derived board layer each cache for one hour; live scores are not cached.
- External ESPN logos can fail independently of the board.
- Play-by-play data can use substantial memory. Supported seasons are hardcoded to **2024–2026**, with a regular-season selector. Statistics through the prior week are available; week 1 has blank prior-week comparisons.
- nfelo is a latest published current snapshot, not a historical archive: the board preserves each team's published source week and may show a mixed source-week range. No future or cross-season ratings are implied, and ratings are not strict historical/pregame values.
- Historical 2024 depth weekly charts have coarse timestamps; newer charts use a timestamp cutoff. Injury snapshots are reconstructed from nflverse's week-by-week reports: weekly designations expire when absent from a later report, while unresolved IR/PUP/NFI/suspension states carry until a source row supersedes them; absence alone is not described as medical recovery. **Pressure %** is the team pressure rate, volume-weighted across quarterbacks within each week and across weeks, not the most-pressured-QB rate.
- Mandatory schedule failures stop with an error. Optional source failures show a warning or missing values rather than silently presenting healthy-looking zeros.

## Maintenance priorities

1. **Highest value / medium risk:** archive point-in-time feeds with coverage metadata, so historical views can be reproduced.
2. **Medium value / low-to-medium risk:** project play-by-play and other heavy data behind measured, lazy-loaded tabs to reduce memory.
3. **Low value / higher churn:** split the large app only if growth requires it. Avoid speculative redesign.

Primary references: [Streamlit Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and the [nfelo README](https://github.com/greerreNFL/nfelo).
