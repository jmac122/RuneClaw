"""Post-notify execution orchestration (handoff §3.5).

Given a scored opportunity, the orchestrator delivers an alert and, depending on
`execution.mode`, queues a pending action and/or invokes the external click actuator:

- ``notify_only``          — deliver + log; nothing queued.
- ``approve_then_execute`` — queue a pending action; wait for manual approval.
- ``auto_execute``         — queue + execute immediately when the verdict clears
                             ``auto_execute_min_verdict``; otherwise leave it pending.

The actuator itself (real OS-level clicks) is Phase 4. Here the ``dry_run`` path is
fully wired: it logs the intended command and completes. With ``dry_run`` off, the
actuator subprocess is invoked; until Phase 4 builds it, that returns a clear error.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from companion.flip_db import FlipDB
from companion.delivery import Notifier
from companion.models import (
    AppConfig,
    ExecutionMode,
    Opportunity,
    PendingAction,
    ScoreResult,
    Verdict,
    meets_min_verdict,
)

log = logging.getLogger("runeclaw.orchestrator")

_TERMINAL_STATUSES = {"done", "failed", "expired", "cancelled"}


class Orchestrator:
    def __init__(
        self,
        config: AppConfig,
        db: FlipDB,
        notifier: Notifier,
        actuator_script: Path,
    ) -> None:
        self._config = config
        self._db = db
        self._notifier = notifier
        self._actuator_script = actuator_script
        execution = config.execution
        self._mode = str(execution.get("mode", ExecutionMode.APPROVE_THEN_EXECUTE.value))
        self._dry_run = bool(execution.get("dry_run", True))
        self._grace = int(execution.get("post_notify_grace_seconds", 300))
        self._min_verdict = Verdict(execution.get("auto_execute_min_verdict", "GOOD"))

    # -- alert handling -------------------------------------------------------

    def handle(self, opp: Opportunity, result: ScoreResult, now: int | None = None) -> str:
        """Process one qualifying opportunity. Returns the outcome label."""
        now = int(time.time()) if now is None else now
        if not self._notifier.should_alert(opp.id, now):
            return "cooldown"

        alert = _build_alert(opp, result)
        if self._mode == ExecutionMode.NOTIFY_ONLY.value:
            self._notifier.notify(alert, now)
            return "notified"

        action = self._create_pending(opp, result, now)
        alert["action_id"] = action.action_id

        if self._mode == ExecutionMode.AUTO_EXECUTE.value:
            if self._config.notify_method != "none":
                self._notifier.notify(alert, now)
            if meets_min_verdict(result.verdict, self._min_verdict):
                self.execute(action.action_id)
                return "executed"
            return "pending"

        # approve_then_execute (default)
        self._notifier.notify(alert, now)
        return "pending"

    def _create_pending(self, opp: Opportunity, result: ScoreResult, now: int) -> PendingAction:
        action = PendingAction(
            action_id=uuid.uuid4().hex[:8],
            created_at=now,
            expires_at=now + self._grace,
            action="place_buy",
            item_id=opp.id,
            name=opp.name,
            price=opp.buy,
            qty=opp.limit or 1,
            slot=None,
            verdict=result.verdict.value,
            status="pending",
        )
        self._db.create_pending(action)
        return action

    # -- approval / execution -------------------------------------------------

    def execute(self, action_id: str) -> dict[str, Any]:
        self._db.expire_stale(int(time.time()))
        action = self._db.get_pending(action_id)
        if action is None:
            return {"status": "error", "error": f"unknown action {action_id}"}
        if action.status in _TERMINAL_STATUSES:
            return {"status": action.status, "error": f"action {action_id} is {action.status}"}
        if action.status == "executing":
            return {"status": "executing", "action_id": action_id}

        self._db.update_status(action_id, "executing")
        outcome = self._invoke_actuator(action)
        if outcome["ok"]:
            self._db.update_status(action_id, "done", completed_at=int(time.time()))
            result: dict[str, Any] = {"status": "done", "action_id": action_id}
            if self._dry_run:
                result["dry_run"] = True
            return result
        self._db.update_status(action_id, "failed", error=outcome["error"])
        return {"status": "failed", "action_id": action_id, "error": outcome["error"]}

    def execute_latest(self) -> dict[str, Any]:
        action = self._db.latest_pending()
        if action is None:
            return {"status": "error", "error": "no pending actions"}
        return self.execute(action.action_id)

    def execute_adhoc(self, body: dict[str, Any]) -> dict[str, Any]:
        """Queue and run an action specified directly (handoff §5.2 POST /execute)."""
        now = int(time.time())
        try:
            action = PendingAction(
                action_id=uuid.uuid4().hex[:8],
                created_at=now,
                expires_at=now + self._grace,
                action=str(body["action"]),
                item_id=int(body["id"]),
                name=str(body.get("name", body["id"])),
                price=int(body["price"]),
                qty=int(body["qty"]),
                slot=body.get("slot"),
                verdict=str(body.get("verdict", "UNKNOWN")),
                status="pending",
            )
        except (KeyError, TypeError, ValueError) as exc:
            return {"status": "error", "error": f"bad request: {exc}"}
        self._db.create_pending(action)
        return self.execute(action.action_id)

    def cancel(self, action_id: str | None = None) -> dict[str, Any]:
        if action_id is None:
            latest = self._db.latest_pending()
            if latest is None:
                return {"status": "error", "error": "no pending actions"}
            action_id = latest.action_id
        action = self._db.get_pending(action_id)
        if action is None:
            return {"status": "error", "error": f"unknown action {action_id}"}
        if action.status in ("pending", "approved"):
            self._db.update_status(action_id, "cancelled")
            return {"status": "cancelled", "action_id": action_id}
        return {"status": action.status, "error": f"cannot cancel {action_id} ({action.status})"}

    # -- actuator subprocess --------------------------------------------------

    def _invoke_actuator(self, action: PendingAction) -> dict[str, Any]:
        cmd = [
            sys.executable,
            str(self._actuator_script),
            "--action", action.action,
            "--item-id", str(action.item_id),
            "--price", str(action.price),
            "--qty", str(action.qty),
        ]
        if action.slot is not None:
            cmd += ["--slot", str(action.slot)]

        if self._dry_run:
            log.info("[dry_run] actuator would run: %s", " ".join(cmd))
            return {"ok": True}

        if not self._actuator_script.exists():
            return {
                "ok": False,
                "error": f"actuator script not found: {self._actuator_script} (build Phase 4)",
            }
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (subprocess.SubprocessError, OSError) as exc:
            return {"ok": False, "error": str(exc)}
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip() or f"actuator exit {proc.returncode}"}
        return {"ok": True}


def _build_alert(opp: Opportunity, result: ScoreResult) -> dict[str, Any]:
    return {
        "ts": int(time.time()),
        "action": "place_buy",
        "item_id": opp.id,
        "name": opp.name,
        "buy": opp.buy,
        "sell": opp.sell,
        "profit": opp.profit,
        "roi": round(opp.roi, 2),
        "verdict": result.verdict.value,
        "reasons": result.reasons,
    }
