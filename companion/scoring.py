"""Buy-quality scorer: GOOD / OK / RISKY / AVOID + reasons (handoff §3.3).

Pure function over already-fetched history, so it is fully unit-testable. Signals:

- **Margin anomaly** (primary trap signal) — current spread vs typical historical spread.
  A spread far above normal usually means a stale/manipulated quote → decisive AVOID.
- **Price percentile** — where the current buy sits in the historical price range.
- **Volume health** — recent vs baseline volume, compared *like-for-like* (same `step`,
  i.e. daily-to-daily) so we never flag everything "thin" (handoff §6.1).
- **Trend** — protects against buying into a sustained decline (falling knife).

History is insufficient → verdict is UNKNOWN, never a fabricated GOOD (handoff error rules).
"""

from __future__ import annotations

from statistics import median

from companion.models import PricePoint, ScoreResult, ScoringParams, Verdict

# Below this typical spread, the anomaly ratio is dominated by rounding noise
# (a 1-2 gp penny margin makes any current spread look like a huge multiple).
_MIN_MARGIN_FOR_ANOMALY = 10
# Trend compares the oldest vs newest quarter of the scored window.
_TREND_WINDOW_DIVISOR = 4
# Volume "recent" window: the last N points (days, for a 24h step).
_RECENT_VOLUME_POINTS = 7


def score_item(
    buy: int, sell: int, history: list[PricePoint], params: ScoringParams
) -> ScoreResult:
    n = len(history)
    if n < params.min_history_points:
        return ScoreResult(
            Verdict.UNKNOWN,
            [f"insufficient history ({n} < {params.min_history_points} points)"],
        )

    lows = [p.avg_low for p in history if p.avg_low is not None]
    margins = [m for p in history if (m := p.margin) is not None and m >= 0]
    vols = [p.volume for p in history]
    if len(lows) < params.min_history_points:
        return ScoreResult(
            Verdict.UNKNOWN, [f"insufficient priced history ({len(lows)} points)"]
        )

    # 1. Margin anomaly — decisive trap signal.
    current_margin = sell - buy
    med_margin = median(margins) if margins else 0
    if med_margin >= _MIN_MARGIN_FOR_ANOMALY and current_margin > 0:
        ratio = current_margin / med_margin
        if ratio >= params.margin_anomaly_ratio:
            return ScoreResult(
                Verdict.AVOID,
                [
                    f"margin {current_margin:,} is {ratio:.1f}x typical "
                    f"{med_margin:,.0f} gp (likely stale/manipulated price)"
                ],
            )

    risk: list[str] = []
    good: list[str] = []
    neutral: list[str] = []

    # 2. Price percentile of the current buy vs historical lows.
    pct = _percentile_rank(buy, lows)
    if pct >= params.buy_high_percentile:
        risk.append(f"buy in top {(1 - pct):.0%} of {len(lows)}-pt price range (expensive)")
    elif pct <= params.buy_low_percentile:
        good.append(f"buy in bottom {pct:.0%} of price range (cheap)")
    else:
        neutral.append(f"buy mid-range ({pct:.0%} percentile)")

    # 3. Volume health — daily-to-daily (handoff §6.1 fix).
    baseline = median(vols)
    recent = median(vols[-min(_RECENT_VOLUME_POINTS, n):])
    if baseline > 0:
        vol_ratio = recent / baseline
        if vol_ratio < params.thin_volume_ratio:
            risk.append(f"recent volume {vol_ratio:.0%} of baseline (thinning)")
        else:
            good.append(f"volume {vol_ratio:.0%} of baseline (healthy)")

    # 4. Trend — avoid buying into a sustained decline.
    trend = _trend(lows)
    if trend is not None:
        if trend <= -params.downtrend_pct:
            risk.append(f"price downtrend {trend:.0%}")
        elif trend >= params.downtrend_pct:
            good.append(f"price uptrend {trend:+.0%}")

    verdict = _combine(len(risk), len(good))
    return ScoreResult(verdict, good + risk + neutral)


def _combine(risk_count: int, good_count: int) -> Verdict:
    if risk_count >= 3:
        return Verdict.AVOID
    if risk_count == 2:
        return Verdict.RISKY
    if risk_count == 1:
        return Verdict.OK if good_count else Verdict.RISKY
    return Verdict.GOOD if good_count else Verdict.OK


def _percentile_rank(value: float, data: list[int]) -> float:
    """Fraction of `data` strictly below `value` (0.0 = cheapest, 1.0 = most expensive)."""
    if not data:
        return 0.5
    return sum(1 for x in data if x < value) / len(data)


def _trend(series: list[int]) -> float | None:
    """Relative change from the oldest to the newest quarter of the window."""
    n = len(series)
    if n < _TREND_WINDOW_DIVISOR:
        return None
    w = max(1, n // _TREND_WINDOW_DIVISOR)
    older = series[:w]
    recent = series[-w:]
    old_mean = sum(older) / len(older)
    if old_mean <= 0:
        return None
    return (sum(recent) / len(recent) - old_mean) / old_mean
