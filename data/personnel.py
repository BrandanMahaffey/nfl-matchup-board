"""Injuries, depth charts, and snap-count helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone

import polars as pl

from data.io import DataLoadError, load_csv
from data.teamref import canonical

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"

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
    "dnp": 2,
    "limited": 3,
    "questionable": 4,
    "ir": 5,
    "pup": 6,
    "nfi": 7,
    "suspended": 8,
}

_OFFICIAL_STATUSES = {"out", "doubtful", "questionable", "ir", "pup", "nfi", "suspended"}
_PERSISTENT_STATUSES = {"ir", "pup", "nfi", "suspended"}

_RESERVE_STATUS_CODES = {
    "R01": "ir",
    "R04": "pup",
    "R05": "nfi",
    "R48": "ir",
}
_DIRECT_ROSTER_STATUSES = {
    "PUP": "pup",
    "RSN": "nfi",
    "SUS": "suspended",
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
            "first_reported_week": pl.Int64,
            "last_reported_week": pl.Int64,
            "is_carried": pl.Boolean,
            "roster_status": pl.String,
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
    """Official game-status bucket from ``report_status``."""
    if status is None:
        return None
    s = status.strip()
    if not s:
        return None
    lower = s.lower()
    if lower in _OFFICIAL_STATUSES:
        return lower
    if "injured reserve" in lower or lower == "ir":
        return "ir"
    if "physically unable" in lower or "pup" in lower:
        return "pup"
    if "non-football" in lower or lower == "nfi":
        return "nfi"
    if "suspend" in lower:
        return "suspended"
    for prefix in ("out", "doubtful", "questionable"):
        if lower.startswith(prefix):
            return prefix
    return None


def _practice_bucket(status: str | None) -> str | None:
    if status is None:
        return None
    lower = status.strip().lower()
    if not lower:
        return None
    if "did not participate" in lower or lower.startswith("dnp"):
        return "dnp"
    if "limited" in lower:
        return "limited"
    if "full particip" in lower:
        return "full"
    return None


def _row_status(report_status: str | None, practice_status: str | None) -> str | None:
    """Game status when posted; otherwise DNP / limited from the practice report."""
    official = _normalize_status(report_status)
    if official:
        return official
    practice = _practice_bucket(practice_status)
    if practice in {"dnp", "limited"}:
        return practice
    return None


def _is_key_position(position: str | None) -> bool:
    if position is None:
        return False
    pos = position.strip().upper()
    return any(pos in group for group in _KEY_POS_GROUPS.values())

def _team_set(teams: list[str]) -> set[str]:
    return {canonical(team) for team in teams}


def _canonicalize_team_column(df: pl.DataFrame) -> pl.DataFrame:
    if "team" not in df.columns:
        raise ValueError("personnel feed is missing required 'team' column")
    return df.with_columns(
        pl.col("team").map_elements(canonical, return_dtype=pl.String).alias("team")
    )


def _normalise_feed_dt(value: object) -> datetime:
    if value is None:
        raise ValueError("depth chart feed contains a null 'dt' value")
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"depth chart feed has invalid 'dt' value: {value!r}") from exc
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    if not isinstance(value, datetime):
        raise ValueError(f"depth chart feed has unsupported 'dt' type: {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        # Historical nflverse files have also arrived as timezone-naive UTC values.
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalise_depth_dates(df: pl.DataFrame) -> pl.DataFrame:
    dtype = df.schema.get("dt")
    if dtype is None:
        raise ValueError("depth chart feed is missing required 'dt' column")
    if not (dtype == pl.String or dtype == pl.Date or isinstance(dtype, pl.Datetime)):
        raise ValueError(f"depth chart feed has unsupported 'dt' schema: {dtype}")
    values = [_normalise_feed_dt(value) for value in df.get_column("dt").to_list()]
    return df.with_columns(pl.Series("_dt_utc", values, dtype=pl.Datetime(time_zone="UTC")))



def _date_modified_key(value: object) -> tuple[int, str]:
    if value is None:
        return (0, "")
    try:
        return (1, _normalise_feed_dt(value).isoformat())
    except (TypeError, ValueError):
        return (1, str(value))


def _full_participation(row: dict) -> bool:
    for value in (row.get("report_status"), row.get("practice_status")):
        text = str(value or "").strip().lower().replace("-", " ")
        if text in {"full", "full participation", "full participant", "active", "healthy"}:
            return True
    return False


def _roster_status(status: object, description_abbr: object) -> str | None:
    status_code = str(status or "").strip().upper()
    if status_code in _DIRECT_ROSTER_STATUSES:
        return _DIRECT_ROSTER_STATUSES[status_code]
    if status_code == "RES":
        return _RESERVE_STATUS_CODES.get(str(description_abbr or "").strip().upper())
    return None


def _injury_identity(row: dict) -> tuple[str, str]:
    team = canonical(row.get("team") or "")
    gid = str(row.get("gsis_id") or "").strip()
    return team, gid or _norm_name(row.get("full_name"))


def _normalise_injury_rows(injuries: pl.DataFrame, through_week=None, teams=None) -> list[dict]:
    allowed = _team_set(teams or []) if teams else None
    rows = []
    for order, source in enumerate(injuries.iter_rows(named=True)):
        row = dict(source)
        row["team"] = canonical(row.get("team") or "")
        season_type = str(row.get("season_type") or "REG").upper()
        if season_type != "REG":
            continue
        try:
            row["week"] = int(row.get("week"))
        except (TypeError, ValueError):
            continue
        if through_week is not None and row["week"] > through_week:
            continue
        if allowed is not None and row["team"] not in allowed:
            continue
        row["_identity"] = _injury_identity(row)
        row["_source_order"] = order
        row["_status_norm"] = _row_status(row.get("report_status"), row.get("practice_status"))
        rows.append(row)
    chosen = {}
    for row in rows:
        key = (row["_identity"], row["week"])
        old = chosen.get(key)
        if old is None or (_date_modified_key(row.get("date_modified")), row["_source_order"]) > (
            _date_modified_key(old.get("date_modified")), old["_source_order"]
        ):
            chosen[key] = row
    return sorted(chosen.values(), key=lambda row: (row["week"], row["_source_order"]))


def injury_state_history(injuries: pl.DataFrame, through_week=None, teams=None) -> list[dict]:
    """Snapshots that retain each team's latest report until that team files again."""
    source = _normalise_injury_rows(injuries, through_week, teams)
    if not source:
        return []
    states, snapshots = {}, []
    first_week = min(row["week"] for row in source)
    last_week = through_week if through_week is not None else max(row["week"] for row in source)
    weeks = range(first_week, last_week + 1)
    for current_week in weeks:
        current_rows = [row for row in source if row["week"] == current_week]
        reported = {row["_identity"] for row in current_rows}
        reporting_teams = {row["team"] for row in current_rows}
        for identity in list(states):
            if (
                states[identity]["_status_norm"] not in _PERSISTENT_STATUSES
                and states[identity]["team"] in reporting_teams
                and identity not in reported
            ):
                del states[identity]
        for row in current_rows:
            identity, status = row["_identity"], row["_status_norm"]
            previous = states.get(identity)
            if status is None:
                if (
                    _full_participation(row)
                    or previous is not None
                    and previous["_status_norm"] not in _PERSISTENT_STATUSES
                ):
                    states.pop(identity, None)
                continue
            item = dict(row)
            item["first_reported_week"] = (
                previous["first_reported_week"]
                if previous is not None and previous["_status_norm"] == status else current_week
            )
            item["last_reported_week"] = current_week
            item["is_carried"] = False
            states[identity] = item
        snapshot = []
        for item in states.values():
            out = {k: v for k, v in item.items() if not k.startswith("_")}
            out["is_carried"] = out["last_reported_week"] != current_week
            snapshot.append(out)
        snapshot.sort(key=lambda row: (row.get("team", ""), row.get("full_name", "")))
        snapshots.append({"week": current_week, "rows": snapshot})
    return snapshots


def derive_injury_states(injuries: pl.DataFrame, through_week: int, teams=None) -> pl.DataFrame:
    history = injury_state_history(injuries, through_week, teams)
    if not history or not history[-1]["rows"]:
        return _empty_injuries()
    return pl.DataFrame(history[-1]["rows"])


def derive_roster_designations(
    rosters: pl.DataFrame,
    through_week: int,
    teams=None,
) -> pl.DataFrame:
    """Current IR/PUP/NFI/suspension state from the weekly roster snapshot."""
    required = {"team", "week", "status", "status_description_abbr"}
    if rosters is None or rosters.is_empty() or not required.issubset(rosters.columns):
        return _empty_injuries()
    allowed = _team_set(teams or []) if teams else None
    histories: dict[tuple[str, str], list[dict]] = {}
    for order, source in enumerate(rosters.iter_rows(named=True)):
        game_type = str(source.get("game_type") or "REG").upper()
        if game_type != "REG":
            continue
        try:
            source_week = int(source.get("week"))
        except (TypeError, ValueError):
            continue
        if source_week > through_week:
            continue
        team = canonical(source.get("team") or "")
        if allowed is not None and team not in allowed:
            continue
        name = source.get("full_name") or source.get("football_name") or ""
        row = {
            "season": source.get("season"),
            "team": team,
            "week": source_week,
            "gsis_id": source.get("gsis_id"),
            "position": source.get("position"),
            "full_name": name,
            "report_status": None,
            "report_primary_injury": None,
            "practice_status": None,
            "_source_order": order,
            "_roster_status": _roster_status(
                source.get("status"),
                source.get("status_description_abbr"),
            ),
        }
        histories.setdefault(_injury_identity(row), []).append(row)

    snapshot_week = max(
        row["week"]
        for history in histories.values()
        for row in history
    ) if histories else None
    current = []
    for history in histories.values():
        history.sort(key=lambda row: (row["week"], row["_source_order"]))
        latest = history[-1]
        if latest["week"] != snapshot_week:
            continue
        roster_status = latest["_roster_status"]
        if roster_status is None:
            continue
        first_week = latest["week"]
        for previous in reversed(history[:-1]):
            if previous["_roster_status"] != roster_status:
                break
            first_week = min(first_week, previous["week"])
        current.append(
            {
                **{k: v for k, v in latest.items() if not k.startswith("_")},
                "first_reported_week": first_week,
                "last_reported_week": latest["week"],
                "is_carried": latest["week"] != through_week,
                "is_key": _is_key_position(latest.get("position")),
                "roster_status": roster_status,
            }
        )
    return pl.DataFrame(current) if current else _empty_injuries()


def _merge_injury_states(injuries: pl.DataFrame, roster: pl.DataFrame) -> pl.DataFrame:
    merged: dict[tuple[str, str], dict] = {}
    for source in injuries.iter_rows(named=True):
        row = dict(source)
        row["roster_status"] = None
        merged[_injury_identity(row)] = row
    for source in roster.iter_rows(named=True):
        row = dict(source)
        identity = _injury_identity(row)
        if identity in merged:
            merged[identity]["roster_status"] = row.get("roster_status")
        else:
            merged[identity] = row
    return pl.DataFrame(list(merged.values())) if merged else _empty_injuries()


def key_injuries(season: int, week: int, teams: list[str]) -> pl.DataFrame:
    injury_url = f"{RELEASE}/injuries/injuries_{season}.csv"
    roster_url = f"{RELEASE}/weekly_rosters/roster_weekly_{season}.csv"
    try:
        injuries = derive_injury_states(load_csv(injury_url), week, teams)
    except DataLoadError:
        injuries = _empty_injuries()
    try:
        roster = derive_roster_designations(load_csv(roster_url), week, teams)
    except DataLoadError:
        roster = _empty_injuries()
    df = _merge_injury_states(injuries, roster)
    if df.is_empty():
        return df
    official = pl.col("report_status").map_elements(_normalize_status, return_dtype=pl.String)
    practice = (
        pl.col("practice_status").map_elements(_practice_bucket, return_dtype=pl.String)
        if "practice_status" in df.columns else pl.lit(None, dtype=pl.String)
    )
    df = df.with_columns(official.alias("_official"), practice.alias("_practice"))
    df = df.with_columns(
        pl.when(pl.col("_official").is_not_null()).then(pl.col("_official"))
        .when(pl.col("_practice").is_in(["dnp", "limited"])).then(pl.col("_practice"))
        .otherwise(None).alias("_status_norm")
    ).filter(
        pl.col("_status_norm").is_not_null() | pl.col("roster_status").is_not_null()
    )
    if df.is_empty():
        return _empty_injuries()
    return df.with_columns(
        pl.col("position").map_elements(_is_key_position, return_dtype=pl.Boolean).alias("is_key"),
        pl.coalesce("_status_norm", "roster_status")
        .replace_strict(_STATUS_ORDER, default=99)
        .alias("_status_rank"),
    ).sort(["_status_rank", "is_key"], descending=[False, True]).drop(
        "_status_norm", "_status_rank", "_official", "_practice"
    )


def last_week_snaps(season: int, week: int, teams: list[str]) -> pl.DataFrame:
    if week <= 1:
        return _empty_snaps()
    snap_week = week - 1

    url = f"{RELEASE}/snap_counts/snap_counts_{season}.csv"
    try:
        df = load_csv(url)
    except DataLoadError:
        return _empty_snaps()
    df = _canonicalize_team_column(df)
    df = df.filter(pl.col("team").is_in(_team_set(teams)), pl.col("week") == snap_week)
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


def depth_starters(
    season: int,
    teams: list[str],
    *,
    week: int,
    as_of: datetime,
) -> pl.DataFrame:
    """Rank-1 depth-chart players from each team's latest chart before a game."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("depth_starters requires a timezone-aware as_of datetime")
    cutoff = as_of.astimezone(timezone.utc)
    url = f"{RELEASE}/depth_charts/depth_charts_{season}.csv"
    try:
        df = load_csv(url)
    except RuntimeError:
        return _empty_starters()
    if df.is_empty():
        return _empty_starters()

    legacy_columns = {"season", "club_code", "week", "game_type", "depth_team",
                      "gsis_id", "position", "depth_position", "full_name"}
    if legacy_columns.issubset(df.columns):
        df = df.filter(
            (pl.col("season") == season)
            & (pl.col("game_type") == "REG")
            & (pl.col("week") <= week)
        )
        df = df.with_columns(
            pl.col("club_code").map_elements(canonical, return_dtype=pl.String).alias("team")
        ).filter(pl.col("team").is_in(_team_set(teams)))
        if df.is_empty():
            return _empty_starters()
        latest = df.group_by("team").agg(pl.col("week").max().alias("_latest_week"))
        df = df.join(latest, on="team", how="inner").filter(
            (pl.col("week") == pl.col("_latest_week"))
            & (pl.col("depth_team").cast(pl.String) == "1")
        )
        if df.is_empty():
            return _empty_starters()
        return (
            df.select(
                "team",
                pl.lit("starter").alias("unit"),
                pl.col("depth_position").alias("pos_abb"),
                pl.col("full_name").alias("player_name"),
                "gsis_id",
                pl.col("position").alias("pos_grp"),
            )
            .sort(["team", "pos_abb", "pos_grp"])
            .unique(subset=["team", "gsis_id"], keep="first")
            .select("team", "unit", "pos_abb", "player_name", "gsis_id")
        )

    df = _canonicalize_team_column(df)
    df = _normalise_depth_dates(df)
    df = df.filter(
        pl.col("team").is_in(_team_set(teams)),
        pl.col("_dt_utc") <= cutoff,
    )
    if df.is_empty():
        return _empty_starters()
    latest = df.group_by("team").agg(pl.col("_dt_utc").max().alias("_latest_dt"))
    df = df.join(latest, on="team", how="inner").filter(pl.col("_dt_utc") == pl.col("_latest_dt"))
    df = df.filter(pl.col("pos_rank") == 1)
    if df.is_empty():
        return _empty_starters()
    return (
        df.sort(["team", "pos_abb", "pos_grp"])
        .unique(subset=["team", "gsis_id"], keep="first")
        .select("team", pl.lit("starter").alias("unit"), "pos_abb", "player_name", "gsis_id")
    )


def injury_records(
    injuries: pl.DataFrame,
    starters: pl.DataFrame,
    snaps: pl.DataFrame,
    team: str,
) -> list[dict]:
    team = canonical(team)
    if injuries is None or injuries.is_empty() or "team" not in injuries.columns:
        return []
    injuries = _canonicalize_team_column(injuries)
    sub = injuries.filter(pl.col("team") == team)
    if sub.is_empty():
        return []
    starter_ids: set[str] = set()
    starter_names: set[str] = set()
    if starters is not None and not starters.is_empty() and "team" in starters.columns:
        starters = _canonicalize_team_column(starters)
        s = starters.filter(pl.col("team") == team)
        if "gsis_id" in s.columns:
            starter_ids = {str(x) for x in s.get_column("gsis_id").drop_nulls().to_list()}
        if "player_name" in s.columns:
            starter_names = {_norm_name(x) for x in s.get_column("player_name").drop_nulls().to_list()}
    if snaps is not None and not snaps.is_empty() and "team" in snaps.columns:
        snaps = _canonicalize_team_column(snaps)
        sn = snaps.filter(pl.col("team") == team)
        if not sn.is_empty() and "player" in sn.columns:
            starter_names |= {_norm_name(x) for x in sn.get_column("player").drop_nulls().to_list()}

    rows: list[dict] = []
    for row in sub.iter_rows(named=True):
        status = _row_status(row.get("report_status"), row.get("practice_status"))
        roster_status = row.get("roster_status")
        if status is None and roster_status is None:
            continue
        name = (row.get("full_name") or "").strip()
        if not name:
            continue
        gid = str(row.get("gsis_id") or "")
        is_starter = (gid and gid in starter_ids) or _norm_name(name) in starter_names
        injury = (row.get("report_primary_injury") or row.get("practice_primary_injury") or "").strip()
        rows.append(
            {
                "team": team,
                "player": name,
                "position": (row.get("position") or "").strip().upper(),
                "status": status,
                "roster_status": roster_status,
                "injury": injury,
                "practice": (row.get("practice_status") or "").strip(),
                "is_starter": is_starter,
                "is_key": bool(row.get("is_key")),
                "first_reported_week": row.get("first_reported_week"),
                "last_reported_week": row.get("last_reported_week"),
                "is_carried": bool(row.get("is_carried", False)),
            }
        )
    rows.sort(
        key=lambda r: (
            0 if r["is_starter"] else 1,
            _STATUS_ORDER.get(r["status"] or r["roster_status"], 9),
            r["player"],
        )
    )
    return rows


def injury_status_counts(records: list[dict]) -> dict[str, int]:
    out = doubtful = questionable = dnp = limited = 0
    for row in records or []:
        status = row.get("status")
        if status == "out":
            out += 1
        elif status == "doubtful":
            doubtful += 1
        elif status == "questionable":
            questionable += 1
        elif status == "dnp":
            dnp += 1
        elif status == "limited":
            limited += 1
    return {
        "out": out,
        "doubtful": doubtful,
        "questionable": questionable,
        "dnp": dnp,
        "limited": limited,
    }


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
