"""Injuries, depth charts, and snap-count helpers."""

from __future__ import annotations

import polars as pl

from data.io import load_csv


RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

_OL_STARTER_POS = {"LT", "LG", "C", "RG", "RT"}
_DL_STARTER_POS = {
    "LDE",
    "RDE",
    "LDT",
    "RDT",
    "NT",
    "LE",
    "RE",
    "DT",
    "LOLB",
    "ROLB",
    "MLB",
    "WLB",
    "SLB",
    "ILB",
    "OLB",
    "DE",
    "EDGE",
}
_DL_FRONT_PREF = ("LDE", "LDT", "RDT", "RDE", "NT", "LOLB", "ROLB")
_DL_KEEP = set(_DL_FRONT_PREF) | {"DE", "DT", "EDGE", "LE", "RE"}

_KEY_POS_GROUPS: dict[str, set[str]] = {
    "QB": {"QB"},
    "OL": {"T", "G", "C", "OT", "OG", "LT", "LG", "RG", "RT", "C"},
    "DL": {"DE", "DT", "NT", "IDL", "EDGE", "OLB", "LDE", "RDE", "LDT", "RDT"},
    "WR": {"WR"},
    "CB": {"CB", "S", "FS", "SS", "DB", "LCB", "RCB"},
}

_STATUS_ORDER = {
    "out": 0,
    "doubtful": 1,
    "questionable": 2,
}


def _empty_injuries() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "season": pl.Int64,
            "team": pl.String,
            "week": pl.Int64,
            "gsis_id": pl.String,
            "position": pl.String,
            "full_name": pl.String,
            "report_status": pl.String,
            "report_primary_injury": pl.String,
            "practice_status": pl.String,
            "is_key": pl.Boolean,
        }
    )


def _empty_starters() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "team": pl.String,
            "unit": pl.String,
            "pos_abb": pl.String,
            "player_name": pl.String,
            "gsis_id": pl.String,
        }
    )


def _empty_snaps() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "team": pl.String,
            "player": pl.String,
            "position": pl.String,
            "offense_snaps": pl.Int64,
            "offense_pct": pl.Float64,
            "defense_snaps": pl.Int64,
            "defense_pct": pl.Float64,
        }
    )


def _normalize_status(status: str | None) -> str | None:
    if status is None:
        return None
    s = status.strip()
    if not s:
        return None
    lower = s.lower()
    if lower in _STATUS_ORDER:
        return lower
    for prefix in ("out", "doubtful", "questionable"):
        if lower.startswith(prefix):
            return prefix
    return None


def _is_key_position(position: str | None) -> bool:
    if position is None:
        return False
    pos = position.strip().upper()
    return any(pos in group for group in _KEY_POS_GROUPS.values())


def key_injuries(season: int, week: int, teams: list[str]) -> pl.DataFrame:
    url = f"{RELEASE}/injuries/injuries_{season}.csv"
    try:
        df = load_csv(url)
    except RuntimeError:
        return _empty_injuries()
    df = df.filter(pl.col("team").is_in(teams), pl.col("week") == week)

    df = df.with_columns(
        pl.col("report_status")
        .map_elements(_normalize_status, return_dtype=pl.String)
        .alias("_status_norm")
    )
    df = df.filter(pl.col("_status_norm").is_not_null())
    df = df.with_columns(
        pl.col("position")
        .map_elements(_is_key_position, return_dtype=pl.Boolean)
        .alias("is_key"),
        pl.col("_status_norm")
        .replace_strict(_STATUS_ORDER, default=99)
        .alias("_status_rank"),
    )
    return df.sort(["_status_rank", "is_key"], descending=[False, True]).drop(
        "_status_norm", "_status_rank"
    )


def injury_flags(injuries_df: pl.DataFrame) -> str:
    if injuries_df.is_empty():
        return ""

    parts: list[str] = []
    for row in injuries_df.filter(pl.col("is_key")).iter_rows(named=True):
        status = _normalize_status(row.get("report_status"))
        if status is None:
            continue
        pos = (row.get("position") or "").strip().upper()
        name = (row.get("full_name") or "").strip()
        if not name:
            continue
        abbr = {"out": "OUT", "doubtful": "D", "questionable": "Q"}[status]
        parts.append(f"{pos} {abbr} {name}")
        if len(parts) >= 6:
            break
    return "; ".join(parts)


def ol_dl_starters(season: int, teams: list[str]) -> pl.DataFrame:
    url = f"{RELEASE}/depth_charts/depth_charts_{season}.csv"
    try:
        df = load_csv(url)
    except RuntimeError:
        return _empty_starters()
    if df.is_empty() or "dt" not in df.columns:
        return _empty_starters()

    latest_dt = df.select(pl.col("dt").max()).item()
    df = df.filter(pl.col("dt") == latest_dt, pl.col("team").is_in(teams))

    ol = df.filter(
        pl.col("pos_abb").is_in(_OL_STARTER_POS), pl.col("pos_rank") == 1
    )
    if not ol.is_empty():
        ol = (
            ol.with_columns(
                pl.col("pos_grp").str.contains("3WR").alias("_has_3wr"),
            )
            .sort(["team", "pos_abb", "_has_3wr"], descending=[False, False, True])
            .unique(subset=["team", "pos_abb"], keep="first")
            .drop("_has_3wr")
        )
    ol = ol.with_columns(pl.lit("ol").alias("unit"))

    dl = df.filter(
        pl.col("pos_abb").is_in(_DL_STARTER_POS), pl.col("pos_rank") == 1
    )
    if not dl.is_empty():
        pref_rank = {p: i for i, p in enumerate(_DL_FRONT_PREF)}
        dl = (
            dl.with_columns(
                pl.col("pos_abb")
                .replace_strict(pref_rank, default=len(_DL_FRONT_PREF))
                .alias("_pref"),
            )
            .sort(["team", "_pref", "pos_abb"])
            .unique(subset=["team", "pos_abb"], keep="first")
            .drop("_pref")
        )
        dl = dl.filter(pl.col("pos_abb").is_in(_DL_KEEP))
    dl = dl.with_columns(pl.lit("dl").alias("unit"))

    out = pl.concat([ol, dl], how="diagonal_relaxed")
    return out.select("team", "unit", "pos_abb", "player_name", "gsis_id")


def last_week_snaps(season: int, week: int, teams: list[str]) -> pl.DataFrame:
    snap_week = week - 1 if week > 1 else 1

    url = f"{RELEASE}/snap_counts/snap_counts_{season}.csv"
    try:
        df = load_csv(url)
    except RuntimeError:
        return _empty_snaps()
    df = df.filter(pl.col("team").is_in(teams), pl.col("week") == snap_week)
    if df.is_empty():
        return _empty_snaps()

    pct_scale = 50.0
    if "offense_pct" in df.columns:
        off = df.get_column("offense_pct").drop_nulls()
        if off.len() and float(off.max()) <= 1.5:
            pct_scale = 0.5
    df = df.filter(
        (pl.col("offense_pct").fill_null(0) >= pct_scale)
        | (pl.col("defense_pct").fill_null(0) >= pct_scale)
    )
    return df.select(
        "team",
        "player",
        "position",
        "offense_snaps",
        "offense_pct",
        "defense_snaps",
        "defense_pct",
    )


def _norm_name(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


def _last_name(value: object) -> str:
    name = str(value or "").strip()
    if not name:
        return ""
    return name.split()[-1]


def depth_starters(season: int, teams: list[str]) -> pl.DataFrame:
    """Every listed rank-1 depth-chart player for ``teams`` (latest chart)."""
    url = f"{RELEASE}/depth_charts/depth_charts_{season}.csv"
    try:
        df = load_csv(url)
    except RuntimeError:
        return _empty_starters()
    if df.is_empty() or "dt" not in df.columns:
        return _empty_starters()
    latest_dt = df.select(pl.col("dt").max()).item()
    df = df.filter(pl.col("dt") == latest_dt, pl.col("team").is_in(teams), pl.col("pos_rank") == 1)
    if df.is_empty():
        return _empty_starters()
    return (
        df.sort(["team", "pos_abb", "pos_grp"])
        .unique(subset=["team", "gsis_id"], keep="first")
        .select(
            "team",
            pl.lit("starter").alias("unit"),
            "pos_abb",
            "player_name",
            "gsis_id",
        )
    )


def injury_records(
    injuries: pl.DataFrame,
    starters: pl.DataFrame,
    snaps: pl.DataFrame,
    team: str,
) -> list[dict]:
    """Structured injury rows; ``is_starter`` uses depth chart or 50%+ snaps."""
    if injuries is None or injuries.is_empty() or "team" not in injuries.columns:
        return []
    sub = injuries.filter(pl.col("team") == team)
    if sub.is_empty():
        return []

    starter_ids: set[str] = set()
    starter_names: set[str] = set()
    if starters is not None and not starters.is_empty() and "team" in starters.columns:
        s = starters.filter(pl.col("team") == team)
        if "gsis_id" in s.columns:
            starter_ids = {str(x) for x in s.get_column("gsis_id").drop_nulls().to_list()}
        if "player_name" in s.columns:
            starter_names = {_norm_name(x) for x in s.get_column("player_name").drop_nulls().to_list()}
    if snaps is not None and not snaps.is_empty() and "team" in snaps.columns:
        sn = snaps.filter(pl.col("team") == team)
        if not sn.is_empty() and "player" in sn.columns:
            starter_names |= {_norm_name(x) for x in sn.get_column("player").drop_nulls().to_list()}

    rows: list[dict] = []
    for row in sub.iter_rows(named=True):
        status = _normalize_status(row.get("report_status"))
        if status is None:
            continue
        name = (row.get("full_name") or "").strip()
        if not name:
            continue
        gid = str(row.get("gsis_id") or "")
        is_starter = (gid and gid in starter_ids) or _norm_name(name) in starter_names
        rows.append(
            {
                "team": team,
                "player": name,
                "position": (row.get("position") or "").strip().upper(),
                "status": status,
                "injury": (row.get("report_primary_injury") or "").strip(),
                "practice": (row.get("practice_status") or "").strip(),
                "is_starter": is_starter,
                "is_key": bool(row.get("is_key")),
            }
        )
    rank = {"out": 0, "doubtful": 1, "questionable": 2}
    rows.sort(key=lambda r: (0 if r["is_starter"] else 1, rank.get(r["status"], 9), r["player"]))
    return rows



def injury_status_counts(records: list[dict]) -> dict[str, int]:
    out = doubtful = questionable = 0
    for row in records or []:
        status = row.get("status")
        if status == "out":
            out += 1
        elif status == "doubtful":
            doubtful += 1
        elif status == "questionable":
            questionable += 1
    return {"out": out, "doubtful": doubtful, "questionable": questionable}


def injury_count_label(records: list[dict]) -> str:
    """Compact OUT / Q counts so the board is never a blank dash."""
    counts = injury_status_counts(records)
    parts = [f"{counts['out']} OUT", f"{counts['questionable']} Q"]
    if counts["doubtful"]:
        parts.insert(1, f"{counts['doubtful']} D")
    return " · ".join(parts)


def starter_out_line(records: list[dict]) -> str:
    """Readable last-name list of starters listed as out."""
    names = [_last_name(r["player"]) for r in records if r.get("is_starter") and r.get("status") == "out"]
    # unique, keep order
    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)
    return " · ".join(ordered)
