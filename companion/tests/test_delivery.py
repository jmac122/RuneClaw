"""Notifier: alerts.jsonl logging and per-item cooldown (handoff §3.5)."""

from __future__ import annotations

import json

from companion.delivery import Notifier
from companion.models import AppConfig


def _config(method: str = "none", cooldown: int = 30) -> AppConfig:
    raw = {
        "notify_method": method,
        "alert_cooldown_minutes": cooldown,
        "discord": {"webhook_url": ""},
    }
    return AppConfig(raw=raw, path="<test>")


def test_alert_appended_to_jsonl(tmp_path) -> None:
    path = tmp_path / "alerts.jsonl"
    notifier = Notifier(_config(), path)
    notifier.notify(
        {"item_id": 4151, "name": "Abyssal whip", "buy": 1000, "sell": 1100,
         "profit": 78, "verdict": "GOOD"}
    )
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["name"] == "Abyssal whip"


def test_cooldown_window(tmp_path) -> None:
    notifier = Notifier(_config(cooldown=30), tmp_path / "alerts.jsonl")
    assert notifier.should_alert(1, now=1000) is True
    notifier.notify({"item_id": 1, "name": "x"}, now=1000)
    assert notifier.should_alert(1, now=1060) is False       # within 30 min
    assert notifier.should_alert(1, now=1000 + 1801) is True  # past 30 min
    assert notifier.should_alert(2, now=1060) is True         # unrelated item
