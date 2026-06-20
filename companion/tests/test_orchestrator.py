"""Execution orchestrator: mode switch, execute/cancel, expiry, cooldown (handoff §3.5)."""

from __future__ import annotations

import json

from companion.delivery import Notifier
from companion.execution_orchestrator import Orchestrator
from companion.flip_db import FlipDB
from companion.models import AppConfig, Opportunity, PendingAction, ScoreResult, Verdict


def _config(
    mode: str, dry_run: bool = True, min_verdict: str = "GOOD", notify: str = "none"
) -> AppConfig:
    raw = {
        "notify_method": notify,
        "alert_cooldown_minutes": 30,
        "discord": {"webhook_url": ""},
        "execution": {
            "mode": mode,
            "dry_run": dry_run,
            "post_notify_grace_seconds": 300,
            "auto_execute_min_verdict": min_verdict,
        },
    }
    return AppConfig(raw=raw, path="<test>")


def _opp() -> Opportunity:
    return Opportunity(
        id=4151, name="Abyssal whip", buy=1000, sell=1100, tax=22,
        profit=78, roi=7.8, limit=70, volume_1h=900,
    )


def _orch(config: AppConfig, db: FlipDB, tmp_path) -> Orchestrator:
    notifier = Notifier(config, tmp_path / "alerts.jsonl")
    return Orchestrator(config, db, notifier, tmp_path / "ge_flip_actuator.py")


def test_notify_only_creates_no_pending(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        orch = _orch(_config("notify_only"), db, tmp_path)
        outcome = orch.handle(_opp(), ScoreResult(Verdict.GOOD, ["r"]))
        assert outcome == "notified"
        assert db.list_pending() == []
        lines = (tmp_path / "alerts.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1


def test_approve_then_execute_queues_pending(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        orch = _orch(_config("approve_then_execute"), db, tmp_path)
        outcome = orch.handle(_opp(), ScoreResult(Verdict.GOOD, ["r"]))
        assert outcome == "pending"
        pend = db.list_pending()
        assert len(pend) == 1
        assert pend[0].action == "place_buy"
        assert pend[0].price == 1000
        assert pend[0].qty == 70  # buy limit
        alert = json.loads((tmp_path / "alerts.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert alert["action_id"] == pend[0].action_id


def test_auto_execute_runs_in_dry_run(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        orch = _orch(_config("auto_execute", dry_run=True), db, tmp_path)
        outcome = orch.handle(_opp(), ScoreResult(Verdict.GOOD, ["r"]))
        assert outcome == "executed"
        assert db.list_pending() == []  # no longer pending
        assert len(db.list_pending(("done",))) == 1


def test_auto_execute_below_min_stays_pending(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        orch = _orch(_config("auto_execute", min_verdict="GOOD"), db, tmp_path)
        outcome = orch.handle(_opp(), ScoreResult(Verdict.OK, ["r"]))
        assert outcome == "pending"
        assert len(db.list_pending()) == 1


def test_execute_marks_done_then_unknown(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        orch = _orch(_config("approve_then_execute"), db, tmp_path)
        orch.handle(_opp(), ScoreResult(Verdict.GOOD, ["r"]))
        action_id = db.latest_pending().action_id
        result = orch.execute(action_id)
        assert result["status"] == "done"
        assert result.get("dry_run") is True
        assert orch.execute("nope")["status"] == "error"


def test_cancel_pending(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        orch = _orch(_config("approve_then_execute"), db, tmp_path)
        orch.handle(_opp(), ScoreResult(Verdict.GOOD, ["r"]))
        action_id = db.latest_pending().action_id
        assert orch.cancel(action_id)["status"] == "cancelled"
        assert db.get_pending(action_id).status == "cancelled"


def test_expired_action_is_not_executed(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        db.create_pending(
            PendingAction(
                action_id="old", created_at=1, expires_at=2, action="place_buy",
                item_id=4151, name="Abyssal whip", price=1000, qty=70, slot=None,
                verdict="GOOD", status="pending",
            )
        )
        orch = _orch(_config("approve_then_execute"), db, tmp_path)
        result = orch.execute("old")  # expires_at far in the past
        assert result["status"] == "expired"


def test_cooldown_blocks_second_alert(tmp_path) -> None:
    with FlipDB(":memory:") as db:
        orch = _orch(_config("approve_then_execute"), db, tmp_path)
        assert orch.handle(_opp(), ScoreResult(Verdict.GOOD, ["r"]), now=1000) == "pending"
        assert orch.handle(_opp(), ScoreResult(Verdict.GOOD, ["r"]), now=1060) == "cooldown"
        assert len(db.list_pending()) == 1  # no duplicate queued
