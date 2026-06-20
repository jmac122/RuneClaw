"""Buy-side signal engine: filters, tax-adjusted margins, ranking (handoff §3.2).

Phase 1: implement evaluate_opportunities here.
"""

from __future__ import annotations

import logging

from companion.models import AppConfig, Opportunity
from companion.wiki_client import WikiClient

log = logging.getLogger("runeclaw.engine")


def evaluate_opportunities(config: AppConfig, wiki: WikiClient) -> list[Opportunity]:
    """Poll Wiki data, apply filters, return ranked opportunities.

    Handoff §3.2 / §7.1:
    - buy = low + undercut, sell = high - undercut
    - reject stale/missing prices, sell <= buy
    - profit/ROI/volume filters from config.filters
    - respect blocklist and watchlist vs scan_all
    """
    raise NotImplementedError("Phase 1: implement evaluate_opportunities (HANDOFF §7.1)")


def format_opportunity_line(opp: Opportunity) -> str:
    limit = opp.limit if opp.limit is not None else "?"
    return (
        f"{opp.name} (id={opp.id})  buy={opp.buy:,}  sell={opp.sell:,}  "
        f"profit={opp.profit:,}/ea  roi={opp.roi:.2f}%  "
        f"vol_1h={opp.volume_1h:,}  limit={limit}"
    )
