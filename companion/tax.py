"""Grand Exchange tax (handoff §4.2, §9)."""

from __future__ import annotations

from typing import Any


def ge_tax(sell: int, name: str, cfg: dict[str, Any]) -> int:
    if sell < cfg["free_below"]:
        return 0
    exempt = {n.lower() for n in cfg.get("exempt_items", [])}
    if name.lower() in exempt:
        return 0
    return min(int(sell * cfg["rate"]), cfg["per_item_cap"])
