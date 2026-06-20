#!/usr/bin/env python3
"""RuneClaw companion watcher — CLI entry (Component B)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import requests

# Allow `python ge_flip_watcher.py` from companion/ without installing the package.
_COMPANION_ROOT = Path(__file__).resolve().parent
if str(_COMPANION_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_COMPANION_ROOT.parent))

from companion.config import default_config_path, load_config, resolve_history_db_path
from companion.engine import evaluate_opportunities, format_opportunity_line
from companion.flip_db import FlipDB
from companion.logging_setup import setup_logging
from companion.models import AppConfig, Opportunity, ScoreResult, ScoringParams, Verdict
from companion.scoring import score_item
from companion.tax import ge_tax
from companion.wiki_client import WikiClient

log = logging.getLogger("runeclaw.cli")


class ItemNotFound(Exception):
    """Raised when a `score`/`backfill` item name or id can't be resolved."""


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
        help="Run a single scan and print ranked, scored opportunities",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max opportunities to print/score (0 = all). Default: 25",
    )
    parser.add_argument(
        "--no-score",
        action="store_true",
        help="Skip scoring and AVOID-suppression in --once (faster raw scan)",
    )
    sub = parser.add_subparsers(dest="command")
    p_back = sub.add_parser(
        "backfill", help="Backfill price history for an item (name or id)"
    )
    p_back.add_argument("item", help="Item name (quoted) or numeric id")
    p_score = sub.add_parser(
        "score", help="Score current buy quality for an item (name or id)"
    )
    p_score.add_argument("item", help="Item name (quoted) or numeric id")
    return parser


# -- item resolution / backfill -------------------------------------------------


def _resolve_item(arg: str, wiki: WikiClient) -> dict[str, Any]:
    """Resolve a CLI item argument (numeric id or exact name) to its mapping entry."""
    mapping = wiki.fetch_mapping()
    if arg.isdigit():
        target_id = int(arg)
        for entry in mapping:
            if entry.get("id") == target_id:
                return entry
        raise ItemNotFound(f"No item with id {target_id}.")
    key = arg.strip().lower()
    for entry in mapping:
        if str(entry.get("name", "")).lower() == key:
            return entry
    raise ItemNotFound(f"No item named {arg!r}. Check spelling and capitalization.")


def _ensure_backfilled(
    db: FlipDB, wiki: WikiClient, entry: dict[str, Any], timestep: str
) -> None:
    """Upsert item metadata and backfill its history once (on first sight)."""
    db.upsert_item(
        entry["id"], entry["name"], entry.get("limit"), _members_int(entry)
    )
    if not db.is_backfilled(entry["id"]):
        points = wiki.fetch_timeseries(entry["id"], timestep)
        db.insert_price_points(entry["id"], points, timestep)
        db.mark_backfilled(entry["id"])


def _members_int(entry: dict[str, Any]) -> int | None:
    members = entry.get("members")
    return None if members is None else int(bool(members))


# -- commands -------------------------------------------------------------------


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

    score_enabled = config.history.get("enabled", True) and not args.no_score
    suppressed = 0
    if score_enabled:
        pairs, suppressed = _score_opportunities(config, wiki, shown)
    else:
        pairs = [(opp, None) for opp in shown]

    summary = [f"{len(pairs)} shown", f"{total} matched"]
    if suppressed:
        summary.append(f"{suppressed} suppressed (AVOID)")
    print(", ".join(summary) + ":")
    for i, (opp, result) in enumerate(pairs, start=1):
        line = format_opportunity_line(opp)
        if result is not None:
            line += f"  [{result.verdict.value}]"
        print(f"{i:>3}. {line}")
    return 0


def _score_opportunities(
    config: AppConfig, wiki: WikiClient, opps: list[Opportunity]
) -> tuple[list[tuple[Opportunity, ScoreResult]], int]:
    """Score the (bounded) displayed opportunities, suppressing AVOID when configured.

    Bounded by design: only the already-matched, already-limited set is scored, so the
    per-item timeseries backfill never runs across the full ~4,500-item catalogue.
    """
    params = ScoringParams.from_config(config)
    timestep = config.history.get("backfill_timestep", "24h")
    pairs: list[tuple[Opportunity, ScoreResult]] = []
    suppressed = 0
    with FlipDB(resolve_history_db_path(config)) as db:
        for opp in opps:
            entry = {"id": opp.id, "name": opp.name, "limit": opp.limit}
            _ensure_backfilled(db, wiki, entry, timestep)
            history = db.get_price_history(opp.id, timestep, params.score_window_points)
            result = score_item(opp.buy, opp.sell, history, params)
            if params.suppress_avoid and result.verdict == Verdict.AVOID:
                suppressed += 1
                continue
            pairs.append((opp, result))
    return pairs, suppressed


def cmd_backfill(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    setup_logging(config)
    wiki = WikiClient(config)
    entry = _resolve_item(args.item, wiki)
    timestep = config.history.get("backfill_timestep", "24h")
    with FlipDB(resolve_history_db_path(config)) as db:
        db.upsert_item(
            entry["id"], entry["name"], entry.get("limit"), _members_int(entry)
        )
        points = wiki.fetch_timeseries(entry["id"], timestep)
        count = db.insert_price_points(entry["id"], points, timestep)
        db.mark_backfilled(entry["id"])
    print(f"Backfilled {entry['name']} (id={entry['id']}): {count} points at {timestep}.")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    setup_logging(config)
    wiki = WikiClient(config)
    entry = _resolve_item(args.item, wiki)
    timestep = config.history.get("backfill_timestep", "24h")
    params = ScoringParams.from_config(config)
    with FlipDB(resolve_history_db_path(config)) as db:
        _ensure_backfilled(db, wiki, entry, timestep)
        history = db.get_price_history(entry["id"], timestep, params.score_window_points)
        latest = wiki.fetch_latest(entry["id"]).get(str(entry["id"]))
        if not latest or latest.get("low") is None or latest.get("high") is None:
            print(f"No current price available for {entry['name']}.", file=sys.stderr)
            return 1
        buy = int(latest["low"]) + config.undercut
        sell = int(latest["high"]) - config.undercut
        result = score_item(buy, sell, history, params)
        tax = ge_tax(sell, entry["name"], config.ge_tax)
        profit = sell - tax - buy
        roi = (profit / buy * 100) if buy > 0 else 0.0
        db.insert_observation(
            entry["id"], buy, sell, sell - buy, profit, roi, None, result.verdict
        )
    print(f"{entry['name']} (id={entry['id']}): {result.verdict.value}")
    print(
        f"  buy={buy:,}  sell={sell:,}  profit={profit:,}/ea  "
        f"history={len(history)} pts ({timestep})"
    )
    for reason in result.reasons:
        print(f"  - {reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "backfill":
            return cmd_backfill(args)
        if args.command == "score":
            return cmd_score(args)
        if args.once:
            return cmd_once(args)
        parser.error("No command. Use --once, or 'backfill <item>' / 'score <item>'.")
    except ItemNotFound as exc:
        print(exc, file=sys.stderr)
        return 1
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
