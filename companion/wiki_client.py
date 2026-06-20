"""OSRS Wiki Real-time Prices API client (handoff §4.1).

Phase 1: implement fetch_mapping, fetch_latest, fetch_1h and bulk helpers here.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from companion.models import AppConfig

log = logging.getLogger("runeclaw.wiki")

WIKI_BASE = "https://prices.runescape.wiki/api/v1/osrs"


class WikiClient:
    def __init__(self, config: AppConfig, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = config.user_agent

    def fetch_mapping(self) -> list[dict[str, Any]]:
        """GET /mapping — cache result in Phase 1 orchestration."""
        raise NotImplementedError("Phase 1: implement fetch_mapping (HANDOFF §4.1)")

    def fetch_latest(self) -> dict[str, dict[str, Any]]:
        """GET /latest — keyed by item id string."""
        raise NotImplementedError("Phase 1: implement fetch_latest (HANDOFF §4.1)")

    def fetch_1h(self) -> dict[str, dict[str, Any]]:
        """GET /1h volume aggregates."""
        raise NotImplementedError("Phase 1: implement fetch_1h (HANDOFF §4.1)")

    def _get(self, path: str) -> Any:
        url = f"{WIKI_BASE}{path}"
        log.debug("GET %s", url)
        response = self._session.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
