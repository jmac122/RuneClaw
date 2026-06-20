from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """Buy-quality verdict (handoff §3.3). Single source of truth for verdict strings."""

    GOOD = "GOOD"
    OK = "OK"
    RISKY = "RISKY"
    AVOID = "AVOID"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PricePoint:
    """One historical aggregate row from `/timeseries` (handoff §5.3 price_history)."""

    item_id: int
    ts: int
    avg_high: int | None
    avg_low: int | None
    high_vol: int
    low_vol: int
    step: str

    @property
    def volume(self) -> int:
        return (self.high_vol or 0) + (self.low_vol or 0)

    @property
    def margin(self) -> int | None:
        if self.avg_high is None or self.avg_low is None:
            return None
        return self.avg_high - self.avg_low


@dataclass(frozen=True)
class ScoreResult:
    """Output of the scorer: a verdict plus human-readable reasons."""

    verdict: Verdict
    reasons: list[str]


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

    @property
    def history(self) -> dict[str, Any]:
        return self.raw.get("history", {})


@dataclass(frozen=True)
class ScoringParams:
    """Scorer thresholds, parsed from config `history` (handoff §5.1)."""

    score_window_points: int
    min_history_points: int
    buy_high_percentile: float
    buy_low_percentile: float
    margin_anomaly_ratio: float
    thin_volume_ratio: float
    downtrend_pct: float
    suppress_avoid: bool

    @classmethod
    def from_config(cls, config: "AppConfig") -> "ScoringParams":
        h = config.history
        return cls(
            score_window_points=int(h.get("score_window_points", 120)),
            min_history_points=int(h.get("min_history_points", 10)),
            buy_high_percentile=float(h.get("buy_high_percentile", 0.85)),
            buy_low_percentile=float(h.get("buy_low_percentile", 0.35)),
            margin_anomaly_ratio=float(h.get("margin_anomaly_ratio", 2.5)),
            thin_volume_ratio=float(h.get("thin_volume_ratio", 0.3)),
            downtrend_pct=float(h.get("downtrend_pct", 0.10)),
            suppress_avoid=bool(h.get("suppress_avoid", True)),
        )
