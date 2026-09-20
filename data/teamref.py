"""Static team reference: names, divisions, colors, logos.

Local lookup table so the UI never waits on a network call for branding.
"""

from __future__ import annotations

from colorsys import hls_to_rgb, rgb_to_hls

_TEAMS: dict[str, tuple[str, str, str, str, str]] = {
    # abbr: (full name, conference, division, primary, secondary)
    "ARI": ("Arizona Cardinals", "NFC", "West", "#97233F", "#FFB612"),
    "ATL": ("Atlanta Falcons", "NFC", "South", "#A71930", "#A5ACAF"),
    "BAL": ("Baltimore Ravens", "AFC", "North", "#241773", "#9E7C0C"),
    "BUF": ("Buffalo Bills", "AFC", "East", "#00338D", "#C60C30"),
    "CAR": ("Carolina Panthers", "NFC", "South", "#0085CA", "#BFC0BF"),
    "CHI": ("Chicago Bears", "NFC", "North", "#C83803", "#0B162A"),
    "CIN": ("Cincinnati Bengals", "AFC", "North", "#FB4F14", "#B0B7BC"),
    "CLE": ("Cleveland Browns", "AFC", "North", "#FF3C00", "#311D00"),
    "DAL": ("Dallas Cowboys", "NFC", "East", "#041E42", "#869397"),
    "DEN": ("Denver Broncos", "AFC", "West", "#FB4F14", "#002244"),
    "DET": ("Detroit Lions", "NFC", "North", "#0076B6", "#B0B7BC"),
    "GB": ("Green Bay Packers", "NFC", "North", "#FFB612", "#203731"),
    "HOU": ("Houston Texans", "AFC", "South", "#A71930", "#03202F"),
    "IND": ("Indianapolis Colts", "AFC", "South", "#002C5F", "#A2AAAD"),
    "JAX": ("Jacksonville Jaguars", "AFC", "South", "#006778", "#D7A22A"),
    "KC": ("Kansas City Chiefs", "AFC", "West", "#E31837", "#FFB81C"),
    "LA": ("Los Angeles Rams", "NFC", "West", "#003594", "#FFD100"),
    "LAC": ("Los Angeles Chargers", "AFC", "West", "#0080C6", "#FFC20E"),
    "LV": ("Las Vegas Raiders", "AFC", "West", "#A5ACAF", "#0A0A0A"),
    "MIA": ("Miami Dolphins", "AFC", "East", "#008E97", "#FC4C02"),
    "MIN": ("Minnesota Vikings", "NFC", "North", "#4F2683", "#FFC62F"),
    "NE": ("New England Patriots", "AFC", "East", "#002244", "#C60C30"),
    "NO": ("New Orleans Saints", "NFC", "South", "#D3BC8D", "#8E8E8E"),
    "NYG": ("New York Giants", "NFC", "East", "#0B2265", "#A71930"),
    "NYJ": ("New York Jets", "AFC", "East", "#125740", "#CFD8DC"),
    "PHI": ("Philadelphia Eagles", "NFC", "East", "#004C54", "#A5ACAF"),
    "PIT": ("Pittsburgh Steelers", "AFC", "North", "#FFB612", "#A5ACAF"),
    "SEA": ("Seattle Seahawks", "NFC", "West", "#69BE28", "#002244"),
    "SF": ("San Francisco 49ers", "NFC", "West", "#AA0000", "#B3995D"),
    "TB": ("Tampa Bay Buccaneers", "NFC", "South", "#D50A0A", "#34302B"),
    "TEN": ("Tennessee Titans", "AFC", "South", "#4B92DB", "#0C2340"),
    "WAS": ("Washington Commanders", "NFC", "East", "#5A1414", "#FFB612"),
}

# nflverse abbreviations that differ from the ESPN logo slugs.
_ESPN_OVERRIDES = {"LA": "lar", "WAS": "wsh"}

# Older abbreviations still present in historical files.
_ALIASES = {"LAR": "LA", "OAK": "LV", "SD": "LAC", "STL": "LA", "WSH": "WAS"}


def canonical(abbr: str | None) -> str:
    key = (abbr or "").strip().upper()
    return _ALIASES.get(key, key)


def team_name(abbr: str | None) -> str:
    """Full club name, falling back to the abbreviation itself."""
    key = canonical(abbr)
    entry = _TEAMS.get(key)
    return entry[0] if entry else key


def division(abbr: str | None) -> str:
    """Conference + division, e.g. ``AFC East``."""
    entry = _TEAMS.get(canonical(abbr))
    return f"{entry[1]} {entry[2]}" if entry else ""


def logo_url(abbr: str | None) -> str:
    key = canonical(abbr)
    if key not in _TEAMS:
        return ""
    slug = _ESPN_OVERRIDES.get(key, key.lower())
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png"


def display_color(abbr: str | None, min_lightness: float = 0.46) -> str:
    """Primary color lifted just enough to stay legible on the dark theme."""
    entry = _TEAMS.get(canonical(abbr))
    if not entry:
        return "#8b98a5"
    return _lighten(entry[3], min_lightness)


def _lighten(hex_color: str, min_lightness: float) -> str:
    raw = hex_color.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))
    h, lightness, s = rgb_to_hls(r, g, b)
    if lightness >= min_lightness:
        return hex_color
    r, g, b = hls_to_rgb(h, min_lightness, max(s, 0.45))
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _hue(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))
    h, _lightness, _s = rgb_to_hls(r, g, b)
    return h * 360.0


def _hue_gap(a: str, b: str) -> float:
    gap = abs(_hue(a) - _hue(b)) % 360.0
    return min(gap, 360.0 - gap)


def pair_colors(away: str | None, home: str | None) -> tuple[str, str]:
    """Two colors that always read as different teams.

    Same-hue matchups (Lions blue vs Bills blue) fall back to the home club's
    secondary color, and then to the theme gold, so comparison bars stay legible.
    """
    a_color = display_color(away)
    h_color = display_color(home)
    if _hue_gap(a_color, h_color) >= 28.0:
        return a_color, h_color

    entry = _TEAMS.get(canonical(home))
    if entry:
        alt = _lighten(entry[4], 0.46)
        if _hue_gap(a_color, alt) >= 28.0:
            return a_color, alt
    return a_color, "#D8A94B" if _hue_gap(a_color, "#D8A94B") >= 28.0 else "#B0B7BC"
