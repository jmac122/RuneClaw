"""Scorer logic: verdicts, reasons, and the trend/anomaly/volume signals (handoff §3.3)."""

from __future__ import annotations

from companion.models import PricePoint, ScoringParams, Verdict
from companion.scoring import _percentile_rank, score_item

_PARAMS = ScoringParams(
    score_window_points=120,
    min_history_points=10,
    buy_high_percentile=0.85,
    buy_low_percentile=0.35,
    margin_anomaly_ratio=2.5,
    thin_volume_ratio=0.3,
    downtrend_pct=0.10,
    suppress_avoid=True,
)


def _pts(
    lows: list[int], margin: int = 20, vols: list[int] | None = None, step: str = "24h"
) -> list[PricePoint]:
    n = len(lows)
    vols = vols if vols is not None else [1000] * n
    return [
        PricePoint(
            item_id=1,
            ts=1_000 + i * 86_400,
            avg_high=lows[i] + margin,
            avg_low=lows[i],
            high_vol=vols[i] // 2,
            low_vol=vols[i] - vols[i] // 2,
            step=step,
        )
        for i in range(n)
    ]


def test_unknown_when_insufficient_history() -> None:
    result = score_item(1000, 1020, _pts([1000] * 5), _PARAMS)
    assert result.verdict is Verdict.UNKNOWN


def test_avoid_on_margin_anomaly() -> None:
    # Typical spread 20; current spread 60 = 3x > 2.5 ratio -> trap.
    result = score_item(1000, 1060, _pts([1000] * 20, margin=20), _PARAMS)
    assert result.verdict is Verdict.AVOID
    assert "margin" in result.reasons[0]


def test_no_false_avoid_on_penny_margin() -> None:
    # Median spread 1 gp is below the absolute floor, so a 10x ratio must NOT trip AVOID.
    result = score_item(100, 110, _pts([100] * 20, margin=1), _PARAMS)
    assert result.verdict is not Verdict.AVOID


def test_good_when_cheap_flat_and_liquid() -> None:
    result = score_item(900, 920, _pts([1000] * 20, margin=20), _PARAMS)
    assert result.verdict is Verdict.GOOD


def test_downtrend_is_not_good_even_when_cheap() -> None:
    # Falling knife: price slid 1500 -> 1000, current buy near the bottom (cheap)
    # but the trend signal must temper it away from GOOD.
    lows = [int(1500 - 500 * i / 39) for i in range(40)]
    result = score_item(1005, 1025, _pts(lows, margin=20), _PARAMS)
    assert result.verdict is not Verdict.GOOD
    assert result.verdict in (Verdict.OK, Verdict.RISKY)
    assert any("downtrend" in r for r in result.reasons)


def test_thin_recent_volume_flagged() -> None:
    vols = [1000] * 13 + [100] * 7  # recent week collapses
    result = score_item(1000, 1020, _pts([1000] * 20, margin=20, vols=vols), _PARAMS)
    assert any("thinning" in r for r in result.reasons)
    assert result.verdict is not Verdict.GOOD


def test_percentile_rank() -> None:
    data = [10, 20, 30, 40]
    assert _percentile_rank(5, data) == 0.0
    assert _percentile_rank(25, data) == 0.5
    assert _percentile_rank(50, data) == 1.0
    assert _percentile_rank(1, []) == 0.5
