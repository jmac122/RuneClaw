"""Load and validate companion config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

from companion.models import AppConfig

_COMPANION_DIR = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _COMPANION_DIR / "config.json"
_EXAMPLE_CONFIG = _COMPANION_DIR / "config.json.example"

_REQUIRED_TOP_LEVEL = (
    "user_agent",
    "filters",
    "ge_tax",
)


def default_config_path() -> Path:
    return _DEFAULT_CONFIG


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else _DEFAULT_CONFIG
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Copy {_EXAMPLE_CONFIG.name} to config.json and set user_agent."
        )
    with config_path.open(encoding="utf-8") as f:
        raw = json.load(f)
    _validate(raw)
    return AppConfig(raw=raw, path=str(config_path.resolve()))


def _validate(raw: dict) -> None:
    missing = [key for key in _REQUIRED_TOP_LEVEL if key not in raw]
    if missing:
        raise ValueError(f"config.json missing required keys: {', '.join(missing)}")
    if "REPLACE_ME" in raw.get("user_agent", ""):
        raise ValueError(
            "Set a descriptive user_agent in config.json "
            '(e.g. "ge-flip-assistant - you@example.com"). See HANDOFF §4.1.'
        )
    filters = raw["filters"]
    for key in (
        "min_profit_per_item",
        "min_roi_pct",
        "min_hourly_volume",
        "min_buy_price",
        "max_buy_price",
        "max_price_age_minutes",
    ):
        if key not in filters:
            raise ValueError(f"config.json filters missing: {key}")


def resolve_data_path(config: AppConfig, key: str, default: str) -> Path:
    """Resolve a config path relative to the config file directory."""
    value = config.raw.get(key, default)
    path = Path(value)
    if not path.is_absolute():
        path = Path(config.path).parent / path
    return path


def ensure_log_dir(config: AppConfig) -> Path | None:
    logging_cfg = config.raw.get("logging", {})
    log_file = logging_cfg.get("file")
    if not log_file:
        return None
    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = Path(config.path).parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path.parent
