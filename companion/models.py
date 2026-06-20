from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """Buy-quality verdict (handoff §3.3). Single source of truth for verdict strings."""

    GOOD = "GOOD"
    OK = "OK"
    RISKY = "RISKY"
    AVOID = "AVOID"
    UNKNOWN = "UNKNOWN"


# Quality ordering for `auto_execute_min_verdict` comparisons (higher = better buy).
VERDICT_RANK: dict[Verdict, int] = {
    Verdict.UNKNOWN: 0,
    Verdict.AVOID: 1,
    Verdict.RISKY: 2,
    Verdict.OK: 3,
    Verdict.GOOD: 4,
}


def meets_min_verdict(verdict: Verdict, minimum: Verdict) -> bool:
    return VERDICT_RANK[verdict] >= VERDICT_RANK[minimum]


class ExecutionMode(str, Enum):
    """Post-notify execution behavior (handoff §3.5)."""

    NOTIFY_ONLY = "notify_only"
    APPROVE_THEN_EXECUTE = "approve_then_execute"
    AUTO_EXECUTE = "auto_execute"


@dataclass(frozen=True)
class PendingAction:
    """A queued GE action awaiting approval/execution (handoff §3.5 / §5.3)."""

    action_id: str
    created_at: int
    expires_at: int
    action: str
    item_id: int
    name: str
    price: int
    qty: int
    slot: int | None
    verdict: str
    status: str
    error: str | None = None
    completed_at: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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

    @property
    def execution(self) -> dict[str, Any]:
        return self.raw.get("execution", {})

    @property
    def notify_method(self) -> str:
        return str(self.raw.get("notify_method", "windows"))

    @property
    def discord_webhook(self) -> str:
        return str(self.raw.get("discord", {}).get("webhook_url", ""))

    @property
    def localhost_port(self) -> int:
        return int(self.raw.get("localhost_port", 8765))

    @property
    def poll_seconds(self) -> int:
        return int(self.raw.get("poll_seconds", 60))

    @property
    def alert_cooldown_minutes(self) -> int:
        return int(self.raw.get("alert_cooldown_minutes", 30))

    @property
    def max_alerts_per_cycle(self) -> int:
        return int(self.raw.get("max_alerts_per_cycle", 3))


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
