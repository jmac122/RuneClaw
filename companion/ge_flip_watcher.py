#!/usr/bin/env python3
"""RuneClaw companion watcher — CLI entry (Component B)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

# Allow `python ge_flip_watcher.py` from companion/ without installing the package.
_COMPANION_ROOT = Path(__file__).resolve().parent
if str(_COMPANION_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_COMPANION_ROOT.parent))

from companion.config import default_config_path, load_config
from companion.engine import evaluate_opportunities, format_opportunity_line
from companion.logging_setup import setup_logging
from companion.wiki_client import WikiClient

log = logging.getLogger("runeclaw.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RuneClaw GE flip companion (Component B)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to config.json (default: companion/config.json)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and print ranked opportunities (Phase 1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max opportunities to print (0 = all). Default: 25",
    )
    return parser


def cmd_once(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    setup_logging(config)
    wiki = WikiClient(config)
    opportunities = evaluate_opportunities(config, wiki)
    if not opportunities:
        log.info("No opportunities matched filters.")
        return 0
    total = len(opportunities)
    shown = opportunities if args.limit <= 0 else opportunities[: args.limit]
    if len(shown) < total:
        print(f"Showing top {len(shown)} of {total} matched opportunities:")
    else:
        print(f"{total} opportunities matched:")
    for i, opp in enumerate(shown, start=1):
        print(f"{i:>3}. {format_opportunity_line(opp)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.once:
        parser.error("No command specified. Use --once for a single scan (Phase 1).")
    try:
        return cmd_once(args)
    except NotImplementedError as exc:
        log.error("%s", exc)
        return 2
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Wiki API request failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
