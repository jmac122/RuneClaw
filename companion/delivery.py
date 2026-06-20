"""Alert delivery: Windows toast / Discord webhook / alerts.jsonl (handoff §3.5).

Every alert is always appended to `alerts.jsonl` (the durable log), regardless of the
notify channel. Per-item cooldown prevents re-alerting the same item too often.
Optional dependencies degrade gracefully: a missing `win11toast` logs and falls back
rather than crashing the watcher.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from companion.models import AppConfig

try:  # optional dependency (Phase 3+); degrade gracefully if absent
    from win11toast import toast as _win_toast
except ImportError:  # pragma: no cover - depends on local install
    _win_toast = None

log = logging.getLogger("runeclaw.delivery")


class Notifier:
    """Sends alerts over the configured channel and records them to `alerts.jsonl`."""

    def __init__(self, config: AppConfig, alerts_path: Path) -> None:
        self._config = config
        self._alerts_path = alerts_path
        self._method = config.notify_method
        self._cooldown_seconds = config.alert_cooldown_minutes * 60
        self._last_alert: dict[int, float] = {}

    def should_alert(self, item_id: int, now: float | None = None) -> bool:
        """False while `item_id` is within its cooldown window."""
        now = time.time() if now is None else now
        last = self._last_alert.get(item_id)
        return last is None or (now - last) >= self._cooldown_seconds

    def notify(self, alert: dict[str, Any], now: float | None = None) -> None:
        """Record the alert to `alerts.jsonl`, mark cooldown, and dispatch to the channel."""
        now = time.time() if now is None else now
        self._append_jsonl(alert)
        item_id = alert.get("item_id")
        if isinstance(item_id, int):
            self._last_alert[item_id] = now
        self._dispatch(alert)

    # -- channels -------------------------------------------------------------

    def _dispatch(self, alert: dict[str, Any]) -> None:
        title, message = _format(alert)
        if self._method == "none":
            return
        if self._method == "discord":
            self._discord(title, message)
        elif self._method == "windows":
            self._windows(title, message)
        else:
            log.warning("Unknown notify_method %r; alert logged only.", self._method)

    def _windows(self, title: str, message: str) -> None:
        if _win_toast is None:
            log.warning("win11toast not installed; toast suppressed: %s — %s", title, message)
            return
        try:
            _win_toast(title, message)
        except Exception as exc:  # toast backends can throw various runtime errors
            log.error("Windows toast failed: %s", exc)

    def _discord(self, title: str, message: str) -> None:
        url = self._config.discord_webhook
        if not url:
            log.warning("notify_method=discord but discord.webhook_url is empty; alert logged only.")
            return
        try:
            requests.post(url, json={"content": f"**{title}**\n{message}"}, timeout=10)
        except requests.RequestException as exc:
            log.error("Discord webhook failed: %s", exc)

    def _append_jsonl(self, alert: dict[str, Any]) -> None:
        self._alerts_path.parent.mkdir(parents=True, exist_ok=True)
        with self._alerts_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(alert) + "\n")


def _format(alert: dict[str, Any]) -> tuple[str, str]:
    verdict = alert.get("verdict", "")
    title = f"{verdict} flip: {alert.get('name', '?')}"
    parts = [
        f"buy {alert.get('buy', 0):,} -> sell {alert.get('sell', 0):,}",
        f"{alert.get('profit', 0):,}/ea",
    ]
    if alert.get("action_id"):
        parts.append(f"approve: execute {alert['action_id']}")
    return title, " | ".join(parts)
