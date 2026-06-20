from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Opportunity:
    """Ranked flip candidate (handoff §4.2 / in-memory shape)."""

    id: int
    name: str
    buy: int
    sell: int
    tax: int
    profit: int
    roi: float
    limit: int | None
    volume_1h: int
    max_profit_4h: int | None = None
    verdict: str | None = None
    verdict_reason: str | None = None


@dataclass(frozen=True)
class AppConfig:
    """Parsed companion config.json."""

    raw: dict[str, Any]
    path: str

    @property
    def user_agent(self) -> str:
        return str(self.raw["user_agent"])

    @property
    def filters(self) -> dict[str, Any]:
        return self.raw["filters"]

    @property
    def ge_tax(self) -> dict[str, Any]:
        return self.raw["ge_tax"]

    @property
    def undercut(self) -> int:
        return int(self.raw.get("undercut", 0))

    @property
    def blocklist(self) -> set[str]:
        return {name.lower() for name in self.raw.get("blocklist", [])}

    @property
    def watchlist(self) -> list[int]:
        return list(self.raw.get("watchlist", []))

    @property
    def scan_all(self) -> bool:
        return bool(self.raw.get("scan_all", True))
