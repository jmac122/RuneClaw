"""OSRS Wiki Real-time Prices API client (handoff §4.1).

All endpoints share one base URL and a descriptive ``User-Agent`` (the Wiki
blocks default/library UAs). ``/latest`` and ``/1h`` wrap their payload in a
top-level ``"data"`` object keyed by item-id string; ``/mapping`` is a bare list.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from companion.models import AppConfig

log = logging.getLogger("runeclaw.wiki")

WIKI_BASE = "https://prices.runescape.wiki/api/v1/osrs"
_TIMEOUT_SECONDS = 30


class WikiClient:
    def __init__(self, config: AppConfig, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = config.user_agent

    def fetch_mapping(self) -> list[dict[str, Any]]:
        """GET /mapping — static item metadata (id, name, limit, members, ...).

        Returned as a bare list; cache once per process (rarely changes).
        """
        payload = self._get("/mapping")
        if not isinstance(payload, list):
            raise ValueError("/mapping did not return a list")
        return payload

    def fetch_latest(self, item_id: int | None = None) -> dict[str, dict[str, Any]]:
        """GET /latest — instabuy/instasell prices keyed by item-id string.

        Pass ``item_id`` to query a single item (``/latest?id=``) instead of all ~4,500.
        """
        path = "/latest" if item_id is None else f"/latest?id={item_id}"
        return self._get_data(path)

    def fetch_1h(self) -> dict[str, dict[str, Any]]:
        """GET /1h — hourly avg price + volume aggregates, keyed by item-id string."""
        return self._get_data("/1h")

    def fetch_timeseries(self, item_id: int, timestep: str) -> list[dict[str, Any]]:
        """GET /timeseries — up to ~365 points for one item at the given timestep.

        ``timestep`` is one of ``5m | 1h | 6h | 24h``. Each point is
        ``{timestamp, avgHighPrice, avgLowPrice, highPriceVolume, lowPriceVolume}``.
        """
        payload = self._get(f"/timeseries?timestep={timestep}&id={item_id}")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise ValueError("/timeseries response missing 'data' list")
        return data

    def _get_data(self, path: str) -> dict[str, dict[str, Any]]:
        payload = self._get(path)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError(f"{path} response missing 'data' object")
        return data

    def _get(self, path: str) -> Any:
        url = f"{WIKI_BASE}{path}"
        log.debug("GET %s", url)
        response = self._session.get(url, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
