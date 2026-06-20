"""Shared logging configuration for companion modules."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from companion.config import AppConfig, ensure_log_dir


def setup_logging(config: AppConfig) -> None:
    logging_cfg = config.raw.get("logging", {})
    level_name = logging_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger("runeclaw")
    root.handlers.clear()
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    log_file = logging_cfg.get("file")
    if log_file:
        ensure_log_dir(config)
        log_path = Path(log_file)
        if not log_path.is_absolute():
            log_path = Path(config.path).parent / log_path
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
