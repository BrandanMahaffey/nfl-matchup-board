"""Color palettes only. No wallpapers."""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class Palette:
    bg: str
    secondary: str
    panel: str
    chip: str
    border: str
    text: str
    muted: str
    accent: str
    hero_at: str
    cmp_num: str
    track: str
    dot: str
    header: str


PALETTES: dict[str, Palette] = {
    "default": Palette(
        bg="#0d1117",
        secondary="#161c24",
        panel="#121820",
        chip="#141b23",
        border="#242e3a",
        text="#e6edf3",
        muted="#8b98a5",
        accent="#d8a94b",
        hero_at="#6f7d8c",
        cmp_num="#93a2b1",
        track="#1a222c",
        dot="#39444f",
        header="#141b23",
    ),
    "light": Palette(
        bg="#f4f2ec",
        secondary="#ffffff",
        panel="#ffffff",
        chip="#ece9e1",
        border="#d3cec3",
        text="#1c1914",
        muted="#6a6459",
        accent="#b8862a",
        hero_at="#8a8378",
        cmp_num="#5c574e",
        track="#e4dfd4",
        dot="#c4beb2",
        header="#ece9e1",
    ),
    "midnight": Palette(
        bg="#070b14",
        secondary="#10182a",
        panel="#0e1628",
        chip="#121c32",
        border="#24314c",
        text="#e8eef8",
        muted="#8b9bb8",
        accent="#7eb0ff",
        hero_at="#6d7d9a",
        cmp_num="#9aabc6",
        track="#172238",
        dot="#3a4a68",
        header="#121c32",
    ),
}

THEME_IDS = {"Default": "default", "Light": "light", "Midnight": "midnight"}
THEME_LABELS = {value: key for key, value in THEME_IDS.items()}


def from_query() -> str:
    raw = str(st.query_params.get("theme") or "default").strip().lower()
    if raw in {"catch", "the-catch", "thecatch"}:
        return "default"
    return raw if raw in PALETTES else "default"


def apply(theme: str) -> None:
    pal = PALETTES.get(theme) or PALETTES["default"]
    css = _CSS.format(**pal.__dict__)
    st.markdown("<style>" + css + "</style>", unsafe_allow_html=True)


_CSS = """
:root {{
  --board-bg: {bg};
  --board-secondary: {secondary};
  --board-panel: {panel};
  --board-chip: {chip};
  --board-border: {border};
  --board-text: {text};
  --board-muted: {muted};
  --board-accent: {accent};
  --board-hero-at: {hero_at};
  --board-cmp-num: {cmp_num};
  --board-track: {track};
  --board-dot: {dot};
  --board-header: {header};
  --background-color: {bg};
  --secondary-background-color: {secondary};
  --text-color: {text};
  --primary-color: {accent};
  --border-color: {border};
}}
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stHeader"], [data-testid="stDecoration"] {{
  background-color: {bg} !important;
  background-image: none !important;
  color: {text} !important;
}}
[data-testid="stHeader"] {{
  background: {bg} !important;
}}
[data-testid="stToolbar"] {{
  background: transparent !important;
}}
.block-container {{
  background: transparent !important;
}}
.masthead h1 {{
  color: {text};
  text-shadow: none;
}}
.masthead .sub, .masthead .sub a {{
  text-shadow: none;
}}
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {{
  background: {panel} !important;
  border: 1px solid {border};
  border-radius: 0.6rem;
}}
[data-testid="stMetric"] {{
  background: {panel};
  border: 1px solid {border};
  border-radius: 0.6rem;
  padding: 0.35rem 0.55rem;
}}
[data-baseweb="tab-list"] {{
  background: {secondary} !important;
  border: 1px solid {border};
  border-radius: 0.5rem;
  padding: 0.15rem;
}}
[data-testid="stSelectbox"] [data-baseweb="select"] > div {{
  background-color: {secondary} !important;
}}
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {{
  background: {panel};
  border: 1px solid {border};
  border-radius: 0.6rem;
  padding: 0.35rem;
}}
label, [data-testid="stWidgetLabel"], [data-testid="stCaptionContainer"],
[data-testid="stMarkdownContainer"], .stMarkdown, .stCaption {{
  color: {text};
}}
[data-testid="stCaptionContainer"], .stCaption {{
  color: {muted} !important;
}}
"""
