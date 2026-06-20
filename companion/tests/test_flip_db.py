"""FlipDB store: insert/read ordering, step isolation, dedupe, backfill flag (§5.3)."""

from __future__ import annotations

from typing import Any

from companion.flip_db import FlipDB
from companion.models import Verdict


def _points(n: int, start_ts: int = 1_000) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": start_ts + i * 86_400,
            "avgHighPrice": 1020 + i,
            "avgLowPrice": 1000 + i,
            "highPriceVolume": 500,
            "lowPriceVolume": 600,
        }
        for i in range(n)
    ]


def test_insert_and_read_chronological() -> None:
    with FlipDB(":memory:") as db:
        db.upsert_item(1, "Test", 100, 0)
        inserted = db.insert_price_points(1, _points(5), "24h")
        assert inserted == 5
        history = db.get_price_history(1, "24h", 10)
        assert len(history) == 5
        assert [p.ts for p in history] == sorted(p.ts for p in history)
        assert history[0].avg_low == 1000
        assert history[0].volume == 1100  # 500 + 600


def test_replace_on_duplicate_ts() -> None:
    with FlipDB(":memory:") as db:
        db.upsert_item(1, "Test", 100, 0)
        db.insert_price_points(
            1, [{"timestamp": 1000, "avgHighPrice": 1020, "avgLowPrice": 1000,
                 "highPriceVolume": 1, "lowPriceVolume": 1}], "24h")
        db.insert_price_points(
            1, [{"timestamp": 1000, "avgHighPrice": 2020, "avgLowPrice": 2000,
                 "highPriceVolume": 9, "lowPriceVolume": 9}], "24h")
        history = db.get_price_history(1, "24h", 10)
        assert len(history) == 1  # replaced, not duplicated
        assert history[0].avg_low == 2000  # latest write wins


def test_step_isolation() -> None:
    with FlipDB(":memory:") as db:
        db.upsert_item(1, "Test", 100, 0)
        db.insert_price_points(1, _points(3), "24h")
        db.insert_price_points(1, _points(3), "1h")
        assert len(db.get_price_history(1, "24h", 10)) == 3
        assert len(db.get_price_history(1, "1h", 10)) == 3


def test_get_price_history_limit_keeps_most_recent() -> None:
    with FlipDB(":memory:") as db:
        db.upsert_item(1, "Test", 100, 0)
        db.insert_price_points(1, _points(10), "24h")
        history = db.get_price_history(1, "24h", 3)
        assert len(history) == 3
        all_ts = sorted(p["timestamp"] for p in _points(10))
        assert [p.ts for p in history] == all_ts[-3:]


def test_backfill_flag_roundtrip() -> None:
    with FlipDB(":memory:") as db:
        db.upsert_item(1, "Test", 100, 0)
        assert db.is_backfilled(1) is False
        db.mark_backfilled(1)
        assert db.is_backfilled(1) is True


def test_upsert_preserves_backfill_and_first_seen() -> None:
    with FlipDB(":memory:") as db:
        db.upsert_item(1, "Test", 100, 0)
        db.mark_backfilled(1)
        db.upsert_item(1, "Test renamed", 200, 1)  # metadata refresh
        assert db.is_backfilled(1) is True  # not reset by re-upsert


def test_insert_observation_smoke() -> None:
    with FlipDB(":memory:") as db:
        db.upsert_item(1, "Test", 100, 0)
        db.insert_observation(1, 1000, 1050, 50, 29, 2.9, 900, Verdict.GOOD)
