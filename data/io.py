"""HTTP CSV loading utilities."""

from __future__ import annotations

import io
from functools import lru_cache

import httpx
import polars as pl


@lru_cache(maxsize=32)
def load_csv(url: str) -> pl.DataFrame:
    """Load a CSV (plain or gzip) from ``url`` into a Polars DataFrame."""
    try:
        response = httpx.get(url, follow_redirects=True, timeout=90.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to load CSV from {url}: {exc}") from exc

    return pl.read_csv(io.BytesIO(response.content), try_parse_dates=True)
