"""HTTP loading utilities for nflverse CSVs and parquet."""

from __future__ import annotations

import io
from urllib.parse import urlsplit

import httpx
import polars as pl
import streamlit as st


class DataLoadError(RuntimeError):
    """A public data source could not be fetched."""


def _source(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.netloc}{parsed.path}" or parsed.netloc or "public data source"


def _fetch(url: str) -> bytes:
    try:
        response = httpx.get(url, follow_redirects=True, timeout=90.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        response = exc.response
        st.warning(
            f"Unable to load public source {_source(url)} "
            f"(HTTP status {response.status_code})."
        )
        raise DataLoadError(
            f"Failed to load public source {_source(url)}: HTTP {response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        st.warning(
            f"Unable to load public source {_source(url)} "
            f"(request error: {type(exc).__name__})."
        )
        raise DataLoadError(
            f"Failed to load public source {_source(url)}: {type(exc).__name__}"
        ) from exc
    return response.content


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def load_csv(url: str) -> pl.DataFrame:
    """Load a CSV (plain or gzip) from ``url`` into a Polars DataFrame."""
    try:
        return pl.read_csv(io.BytesIO(_fetch(url)), try_parse_dates=True)
    except pl.exceptions.PolarsError as exc:
        st.warning(f"Unable to load public source {_source(url)} (invalid CSV data).")
        raise DataLoadError(
            f"Failed to load public source {_source(url)}: invalid CSV data"
        ) from exc


@st.cache_data(ttl=3600, max_entries=16, show_spinner=False)
def load_parquet(url: str) -> pl.DataFrame:
    """Load a parquet file from ``url`` into a Polars DataFrame."""
    try:
        return pl.read_parquet(io.BytesIO(_fetch(url)))
    except pl.exceptions.PolarsError as exc:
        st.warning(
            f"Unable to load public source {_source(url)} (invalid Parquet data)."
        )
        raise DataLoadError(
            f"Failed to load public source {_source(url)}: invalid Parquet data"
        ) from exc
