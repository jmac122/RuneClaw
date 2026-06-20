"""Engine filter / tax-adjusted profit / ranking logic (handoff §7.1).

Tests target the pure ``rank_opportunities`` so no network access is needed.
A fixed ``now`` makes the freshness filter deterministic.
"""

from __future__ import annotations

from typing import Any

from companion.engine import rank_opportunities
from companion.models import AppConfig

_NOW = 1_700_000_000.0  # fixed clock for deterministic freshness checks

_BASE_CONFIG = {
    "user_agent": "ge-flip-assistant - test@example.com",
    "scan_all": True,
    "watchlist": [],
    "blocklist": ["Old school bond"],
    "undercut": 0,
    "filters": {
        "min_profit_per_item": 50,
        "min_roi_pct": 1.5,
        "min_hourly_volume": 200,
        "min_buy_price": 100,
        "max_buy_price": 50_000_000,
        "max_price_age_minutes": 30,
    },
    "ge_tax": {
        "rate": 0.02,
        "per_item_cap": 5_000_000,
        "free_below": 50,
        "exempt_items": ["Old school bond"],
    },
}


def _config(**overrides: Any) -> AppConfig:
    raw = {**_BASE_CONFIG, **overrides}
    return AppConfig(raw=raw, path="<test>")


def _fresh(low: int, high: int, age_seconds: int = 0) -> dict[str, Any]:
    ts = _NOW - age_seconds
    return {"low": low, "high": high, "lowTime": ts, "highTime": ts}


def _vol(high_vol: int, low_vol: int) -> dict[str, Any]:
    return {"highPriceVolume": high_vol, "lowPriceVolume": low_vol}


def _mapping(item_id: int, name: str, limit: int | None = 1000) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": item_id, "name": name}
    if limit is not None:
        entry["limit"] = limit
    return entry


def test_good_opportunity_passes_with_correct_math() -> None:
    mapping = [_mapping(4151, "Abyssal whip", limit=70)]
    latest = {"4151": _fresh(low=1_000_000, high=1_050_000)}
    hourly = {"4151": _vol(500, 400)}

    opps = rank_opportunities(_config(), mapping, latest, hourly, now=_NOW)

    assert len(opps) == 1
    opp = opps[0]
    assert opp.buy == 1_000_000
    assert opp.sell == 1_050_000
    assert opp.tax == 21_000  # floor(1_050_000 * 0.02)
    assert opp.profit == 1_050_000 - 21_000 - 1_000_000  # 29_000
    assert round(opp.roi, 2) == round(29_000 / 1_000_000 * 100, 2)
    assert opp.volume_1h == 900
    assert opp.max_profit_4h == 29_000 * 70


def test_stale_price_rejected() -> None:
    mapping = [_mapping(2, "Cannonball")]
    latest = {"2": _fresh(low=180, high=200, age_seconds=31 * 60)}
    hourly = {"2": _vol(5000, 5000)}

    assert rank_opportunities(_config(), mapping, latest, hourly, now=_NOW) == []


def test_below_profit_threshold_rejected() -> None:
    mapping = [_mapping(2, "Cannonball")]
    latest = {"2": _fresh(low=200, high=210)}  # profit < 50 after tax
    hourly = {"2": _vol(5000, 5000)}

    assert rank_opportunities(_config(), mapping, latest, hourly, now=_NOW) == []


def test_one_sided_volume_rejected() -> None:
    mapping = [_mapping(4151, "Abyssal whip", limit=70)]
    latest = {"4151": _fresh(low=1_000_000, high=1_050_000)}
    hourly = {"4151": _vol(5000, 0)}  # nobody instasells -> cannot buy in

    assert rank_opportunities(_config(), mapping, latest, hourly, now=_NOW) == []


def test_thin_total_volume_rejected() -> None:
    mapping = [_mapping(4151, "Abyssal whip", limit=70)]
    latest = {"4151": _fresh(low=1_000_000, high=1_050_000)}
    hourly = {"4151": _vol(80, 80)}  # 160 total < 200 floor

    assert rank_opportunities(_config(), mapping, latest, hourly, now=_NOW) == []


def test_blocklist_rejected() -> None:
    mapping = [_mapping(13190, "Old school bond", limit=10)]
    latest = {"13190": _fresh(low=8_000_000, high=8_500_000)}
    hourly = {"13190": _vol(500, 500)}

    assert rank_opportunities(_config(), mapping, latest, hourly, now=_NOW) == []


def test_inverted_price_rejected() -> None:
    mapping = [_mapping(2, "Cannonball")]
    latest = {"2": _fresh(low=210, high=200)}  # sell <= buy
    hourly = {"2": _vol(5000, 5000)}

    assert rank_opportunities(_config(), mapping, latest, hourly, now=_NOW) == []


def test_watchlist_restricts_when_scan_all_false() -> None:
    mapping = [
        _mapping(4151, "Abyssal whip", limit=70),
        _mapping(11802, "Armadyl godsword", limit=8),
    ]
    latest = {
        "4151": _fresh(low=1_000_000, high=1_050_000),
        "11802": _fresh(low=15_000_000, high=15_800_000),
    }
    hourly = {"4151": _vol(500, 400), "11802": _vol(300, 300)}

    config = _config(scan_all=False, watchlist=[11802])
    opps = rank_opportunities(config, mapping, latest, hourly, now=_NOW)

    assert [o.id for o in opps] == [11802]


def test_watchlist_accepts_names() -> None:
    mapping = [
        _mapping(4151, "Abyssal whip", limit=70),
        _mapping(11802, "Armadyl godsword", limit=8),
    ]
    latest = {
        "4151": _fresh(low=1_000_000, high=1_050_000),
        "11802": _fresh(low=15_000_000, high=15_800_000),
    }
    hourly = {"4151": _vol(500, 400), "11802": _vol(300, 300)}

    config = _config(scan_all=False, watchlist=["abyssal whip"])
    opps = rank_opportunities(config, mapping, latest, hourly, now=_NOW)

    assert [o.id for o in opps] == [4151]


def test_ranking_orders_by_potential_profit() -> None:
    # Whip: profit 29_000 * limit 70 = 2_030_000 potential.
    # AGS:  profit 484_000 * limit 8 = 3_872_000 potential -> ranks first.
    mapping = [
        _mapping(4151, "Abyssal whip", limit=70),
        _mapping(11802, "Armadyl godsword", limit=8),
    ]
    latest = {
        "4151": _fresh(low=1_000_000, high=1_050_000),
        "11802": _fresh(low=15_000_000, high=15_800_000),
    }
    hourly = {"4151": _vol(500, 400), "11802": _vol(300, 300)}

    opps = rank_opportunities(_config(), mapping, latest, hourly, now=_NOW)

    assert [o.id for o in opps] == [11802, 4151]
