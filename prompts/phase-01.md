# Phase 1 — Engine core

Paste this into Claude Code to implement Build Phase 1.

---

Implement **HANDOFF_ge_flip_assistant.md Build Phase 1 (§7.1)**. Follow **CLAUDE.md**.

## Context

- Repo scaffold exists under `companion/` — extend it, do not replace the layout.
- `companion/tax.py` and `companion/tests/test_tax.py` are done — do not rewrite unless fixing bugs.
- `companion/wiki_client.py` and `companion/engine.py` are stubs — **implement these**.
- `companion/config.py`, `companion/models.py`, `companion/logging_setup.py` are in place.

## Implement

1. **`companion/wiki_client.py`**
   - `fetch_mapping()` → GET `/mapping`, return list (~4500 items)
   - `fetch_latest()` → GET `/latest`, return `data` dict keyed by item id
   - `fetch_1h()` → GET `/1h`, return `data` dict
   - Use `_get()` helper; descriptive User-Agent from config; handle 5xx/timeouts with log + re-raise or empty fallback per handoff §3.2 edge cases
   - Do **not** loop per-item `id` queries — bulk endpoints only (§4.1)

2. **`companion/engine.py` — `evaluate_opportunities()`**
   - Per handoff §3.2: `buy = low + undercut`, `sell = high - undercut`
   - Reject missing prices, `sell <= buy`, stale `highTime`/`lowTime` vs `max_price_age_minutes`
   - `profit = sell - tax(sell) - buy` using `companion.tax.ge_tax`
   - Filter: min profit, ROI, hourly volume (`min(highPriceVolume, lowPriceVolume)` from `/1h`)
   - Price band, blocklist, `scan_all` vs `watchlist`
   - Return `list[Opportunity]` sorted by profit descending (or ROI — pick one, document it)

3. **Wire `ge_flip_watcher.py --once`** — should print ranked lines via `format_opportunity_line`

## Out of scope

- SQLite / scorer (Phase 2)
- Notifications / actuator / HTTP API (Phases 3–4)
- RuneLite plugin
- Copilot/FU parsers

## Verify

```bash
cd companion
pip install -r requirements.txt
cp config.json.example config.json   # if config.json missing; set real user_agent
pytest tests -q
python ge_flip_watcher.py --once
```

**Done when:** `--once` prints sane tax-adjusted opportunities against the live Wiki API.

Summarize changes, show sample `--once` output, and note anything blocked for Phase 2.
