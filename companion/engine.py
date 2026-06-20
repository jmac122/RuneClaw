"""Buy-side signal engine: filters, tax-adjusted margins, ranking (handoff §3.2 / §7.1).

The work is split so the decision logic is pure and unit-testable:

- ``evaluate_opportunities`` does the I/O (three bulk Wiki fetches) and delegates.
- ``rank_opportunities`` is a pure function over already-fetched data + config.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from companion.models import AppConfig, Opportunity
from companion.tax import ge_tax
from companion.wiki_client import WikiClient

log = logging.getLogger("runeclaw.engine")


def evaluate_opportunities(config: AppConfig, wiki: WikiClient) -> list[Opportunity]:
    """Fetch live Wiki data and return ranked, filtered flip opportunities."""
    mapping = wiki.fetch_mapping()
    latest = wiki.fetch_latest()
    hourly = wiki.fetch_1h()
    log.info(
        "Fetched %d mapped items, %d latest prices, %d hourly aggregates.",
        len(mapping),
        len(latest),
        len(hourly),
    )
    return rank_opportunities(config, mapping, latest, hourly)


def rank_opportunities(
    config: AppConfig,
    mapping: list[dict[str, Any]],
    latest: dict[str, dict[str, Any]],
    hourly: dict[str, dict[str, Any]],
    now: float | None = None,
) -> list[Opportunity]:
    """Join the three Wiki datasets by item id, filter, and rank by potential profit.

    Each mapping entry supplies the item's name + 4h buy limit; ``latest`` supplies
    the instabuy/instasell prices; ``hourly`` supplies traded volume. Items are kept
    only when every filter in ``config.filters`` passes (handoff §7.1).
    """
    now = time.time() if now is None else now
    filters = config.filters
    tax_cfg = config.ge_tax
    blocklist = config.blocklist
    # watchlist entries may be item ids (int) or names (str), mirroring blocklist
    # which matches by name — avoids a silent "everything filtered" foot-gun.
    watch_ids = {w for w in config.watchlist if isinstance(w, int)}
    watch_names = {str(w).lower() for w in config.watchlist if not isinstance(w, int)}
    scan_all = config.scan_all
    undercut = config.undercut
    max_age_seconds = float(filters["max_price_age_minutes"]) * 60

    opportunities: list[Opportunity] = []
    for entry in mapping:
        item_id = entry.get("id")
        name = entry.get("name")
        if item_id is None or name is None:
            continue
        name_lower = name.lower()
        if not scan_all and item_id not in watch_ids and name_lower not in watch_names:
            continue
        if name_lower in blocklist:
            continue

        opp = _evaluate_item(
            item_id=int(item_id),
            name=str(name),
            limit=entry.get("limit"),
            price=latest.get(str(item_id)),
            volume=hourly.get(str(item_id)),
            filters=filters,
            tax_cfg=tax_cfg,
            undercut=undercut,
            now=now,
            max_age_seconds=max_age_seconds,
        )
        if opp is not None:
            opportunities.append(opp)

    opportunities.sort(key=_rank_key, reverse=True)
    return opportunities


def _evaluate_item(
    *,
    item_id: int,
    name: str,
    limit: Any,
    price: dict[str, Any] | None,
    volume: dict[str, Any] | None,
    filters: dict[str, Any],
    tax_cfg: dict[str, Any],
    undercut: int,
    now: float,
    max_age_seconds: float,
) -> Opportunity | None:
    """Return an Opportunity for one item, or None if any filter rejects it."""
    if not price:
        return None
    low = price.get("low")
    high = price.get("high")
    low_time = price.get("lowTime")
    high_time = price.get("highTime")
    if low is None or high is None or low_time is None or high_time is None:
        return None
    # Need both a fresh instasell (buy target) and instabuy (sell target).
    if now - low_time > max_age_seconds or now - high_time > max_age_seconds:
        return None

    buy = int(low) + undercut
    sell = int(high) - undercut
    if sell <= buy or buy <= 0:
        return None
    if buy < filters["min_buy_price"] or buy > filters["max_buy_price"]:
        return None

    tax = ge_tax(sell, name, tax_cfg)
    profit = sell - tax - buy
    if profit < filters["min_profit_per_item"]:
        return None
    roi = profit / buy * 100
    if roi < filters["min_roi_pct"]:
        return None

    high_vol = int(volume.get("highPriceVolume") or 0) if volume else 0
    low_vol = int(volume.get("lowPriceVolume") or 0) if volume else 0
    # A completable flip needs liquidity on both sides; reject one-sided items
    # outright, then gate total hourly volume against the configured floor.
    if high_vol <= 0 or low_vol <= 0:
        return None
    volume_1h = high_vol + low_vol
    if volume_1h < filters["min_hourly_volume"]:
        return None

    buy_limit = int(limit) if limit else None
    max_profit_4h = profit * buy_limit if buy_limit else None
    return Opportunity(
        id=item_id,
        name=name,
        buy=buy,
        sell=sell,
        tax=tax,
        profit=profit,
        roi=roi,
        limit=buy_limit,
        volume_1h=volume_1h,
        max_profit_4h=max_profit_4h,
    )


def _rank_key(opp: Opportunity) -> tuple[int, float]:
    """Rank by potential profit per 4h buy-limit window, tie-broken by ROI.

    Items without a known buy limit fall back to per-item profit so they still
    sort sensibly, generally below limited items with real total potential.
    """
    primary = opp.max_profit_4h if opp.max_profit_4h is not None else opp.profit
    return (primary, opp.roi)


def format_opportunity_line(opp: Opportunity) -> str:
    limit = opp.limit if opp.limit is not None else "?"
    return (
        f"{opp.name} (id={opp.id})  buy={opp.buy:,}  sell={opp.sell:,}  "
        f"profit={opp.profit:,}/ea  roi={opp.roi:.2f}%  "
        f"vol_1h={opp.volume_1h:,}  limit={limit}"
    )
