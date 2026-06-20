# OSRS GE Flip Assistant — Developer Handoff Specification

**Audience:** a local Claude Code session that will implement this.
**Status of facts below:** items marked **[VERIFIED]** were confirmed against live
sources/APIs during research and tested. Items marked **[CONFIRM]** must be
validated locally before relying on them. Do not re-derive **[VERIFIED]** facts.

---

## 0. Scope & Hard Boundaries — read first

**What this is:** a local, *advisory* OSRS Grand Exchange flipping assistant. It
watches public price data and the user's own flipping-plugin data, decides what to
buy/sell and when, scores whether a buy is good or a trap, and **notifies the user**.
The user places every Grand Exchange offer by hand.

**Supports two plugins behind a small adapter layer** (see §2): **Flipping Utilities**
(a tracker — our Wiki engine generates the signals) and **Flipping Copilot** (an AI
assistant whose backend already generates signals — we read/augment/deliver/control).
A standalone mode (no plugin) uses the Wiki engine alone.

**The one hard line:** the system advises and *prepares* the trade — it can suggest,
score, pre-fill the GE offer, and highlight where to act (exactly the in-client behavior
Copilot already ships and the Plugin Hub allows). It must **not** perform the actual
click/keypress that places or confirms an offer, and must not synthesize input into the
live client (pyautogui / AutoHotkey / Desktop Commander / Windows MCP / OpenClaw
clickers). The human does that final actuation. That is the only boundary.

**Conventions:**
- Do **not** add any AI/assistant attribution or "Co-authored-by"/"Generated with"
  trailers to commits or PRs.
- Discord: if reading a channel, use a **bot** token in a server you own (not a user token).
- Python 3.11+, stdlib `sqlite3`, `requests`; optional `win11toast`, `discord.py`.
  Config in one hot-reloaded `config.json`. No secrets in code.

---

## 1. Confirmed Ground Truth (don't re-derive)

### 1.1 OSRS Wiki Real-time Prices API **[VERIFIED]**
- Base: `https://prices.runescape.wiki/api/v1/osrs`
- **User-Agent is required and must be descriptive** (e.g. `"ge-flip-assistant - you@example.com"`).
  The API pre-emptively blocks default/library user-agents. Do not loop the `id`
  param over all items; fetch bulk endpoints instead.
- Data is built from **completed RuneLite trades only** (not the official/mobile
  client), so it lags slightly and won't cover every item.
- Endpoints and shapes:
  - `GET /mapping` → list of `{id, name, members, limit, value, lowalch, highalch, examine, icon}`. `limit` = 4-hour GE buy limit (may be missing). ~4,500 items.
  - `GET /latest` → `{"data": {"<id>": {high, highTime, low, lowTime}}}`.
    **Semantics:** `high` = most recent **instabuy** price (your sell target);
    `low` = most recent **instasell** price (your buy target). For a flip:
    **buy ≈ low, sell ≈ high.** `highTime`/`lowTime` are unix seconds.
  - `GET /1h`, `GET /5m`, `GET /24h` → `{"data": {"<id>": {avgHighPrice, avgLowPrice, highPriceVolume, lowPriceVolume}}}`.
  - `GET /timeseries?timestep={5m|1h|6h|24h}&id={id}` → up to ~300 points of
    `{timestamp, avgHighPrice, avgLowPrice, highPriceVolume, lowPriceVolume}`.
    `timestep=24h` yields ~365 daily points (verified), giving an instant ~1-year
    history per item with no waiting.

### 1.2 Grand Exchange tax **[VERIFIED]**
- 2% of the **sell** price, **floored per item**, **capped at 5,000,000 gp/item**.
- Items selling **below 50 gp** pay 0 (2% floors to 0). Bonds and a small fixed list
  are fully exempt. Buyers pay no tax.
- `profit_per_item = sell - tax(sell) - buy`, where
  `tax(sell) = 0 if (exempt or sell < 50) else min(floor(sell*0.02), 5_000_000)`.
- Verified outputs: `tax(1250)=25`, `tax(49)=0`, `tax(300_000_000)=5_000_000`,
  `tax(bond)=0`.

### 1.3 Flipping Utilities local data **[VERIFIED location/nesting; CONFIRM field names]**
- Path: `~/.runelite/flipping/<account_username>.json` (one file per OSRS account).
- It is a serialized `AccountData` object. Key nesting:
  `AccountData.trades` → `List<FlippingItem>`; each `FlippingItem.history` is a
  `HistoryManager` ≈ a list of `OfferEvent`; each `OfferEvent` has price, quantity,
  a buy/sell flag, and a timestamp.
- **Written on logout / client shutdown** (mutated in memory during play). So the
  on-disk file can be stale mid-session; it is freshest right after a logout/hop.
- **[CONFIRM]** The exact on-disk JSON field names and whether `OfferEvent`s are
  stored raw or in a compressed/cumulative form. `GrandExchangeOfferChanged` events
  fire repeatedly per offer (cumulative state updates, not discrete fills), so the
  history may contain cumulative/duplicate entries that must be normalized. **Do not
  guess the schema — require a real (redacted) snippet of one `trades[]` entry and
  its `history` before writing the parser.**

### 1.4 osrs.cloud / Flipping Utilities premium **[VERIFIED]**
- `prices.osrs.cloud` (and `osrs.cloud`) is the Flipping Utilities web/community
  service: a price site, the **Flopper** Discord bot, and the RuneLite plugin, tied
  to `discord.gg/flipping`.
- Premium users can track in-game offers and **receive offer-fulfilled notifications
  via the Discord bot**. No public API documentation was found; the site is
  JS-rendered and feature-gated behind their Discord (not scrapable).
- **No evidence** that premium can deliver alerts to a **custom webhook / the user's
  own server**. Treat FU-alert ingestion as optional and gated on confirming such a
  feature exists (§3.7). The local signal engine (§3.1–3.2) makes it unnecessary.

### 1.5 OpenClaw Windows node **[VERIFIED capabilities; CONFIRM notify invocation]**
- Node Mode lets the OpenClaw agent drive the Windows PC via declared capabilities,
  gated by an allowlist in `~/.openclaw/openclaw.json` under `gateway.nodes.allowCommands`
  (explicit names; wildcards don't work) and a gateway pairing.
- Relevant capabilities: `system.notify` (Windows toast), `system.run` (run a command
  under policy), `screen.snapshot`, `tts.speak`, `canvas.*`. It can also expose a
  local MCP server on loopback.
- **There is no native mouse/keyboard input primitive** — any "click" would be an
  external script invoked via `system.run` (which is in the non-goals; don't).
- **[CONFIRM]** The exact mechanism for a *script* to trigger `system.notify` on the
  node (gateway endpoint/MCP call shape) was not verified. Prefer the script-emits +
  agent-tails pattern, or direct Windows toast, until confirmed (§3.4).

### 1.6 Flipping Copilot **[VERIFIED architecture; CONFIRM exact JSON fields]**
- Repo `cbrewitt/flipping-copilot` (author Cillian), RuneLite Plugin Hub, v1.7.20, Java 11.
- **Opposite of FU under the hood:** Copilot's buy/sell/abort **suggestions are
  generated server-side** by `api.flippingcopilot.com` (JWT auth; MessagePack payloads)
  from live game state (inventory, offers, slots, gold) + preferences, and shown in
  its SuggestionPanel + in-game overlays. **Copilot already does the signal generation**
  our Wiki engine does for FU. For Copilot users, this system reads, augments (scores),
  delivers, and controls — it does not re-derive Copilot's picks.
- **Local storage dir:** `~/.runelite/flipping-copilot/`
  (`RuneLite.RUNELITE_DIR/flipping-copilot/`). Files (names/content VERIFIED; exact
  field names CONFIRM):
  - `login-response.json` — JWT token, user ID, **premium status**.
  - `acc_{accountHash}_{slot}.json` — cached `SavedOffer` per GE slot (0–7):
    item id, price, quantity, state. **= your current open-offer / GE state.**
  - `{displayNameSHA1}_un_acked.jsonl` — recent completed `Transaction`s not yet synced
    (JSONL, deduped by UUID) = buy/sell fills.
  - `{displayNameSHA1}_session_data.jsonl` — session start, durationMillis, averageCash.
  - `{profileName}.profile.json` — preferences incl. **blocked items** + risk settings;
    atomic writes w/ `.lock`; **Copilot reloads it every ~5 s**, so external edits apply
    live. **This is Copilot's native blocklist.**
  - Completed flip history is cloud-synced (`FlipManager`; `POST /profit-tracking/
    client-flips-delta`); a local cache (e.g. `flips_{accountId}.json`) may exist **[CONFIRM]**.
  - Filenames: `accountHash = client.getAccountHash()`; `displayNameSHA1 = SHA1(display name)`.
- **Discord:** Copilot's `WebHookController` natively posts **session stats / flip
  summaries to a Discord webhook you configure** (your own server — clean). It does not
  clearly push per-suggestion buy alerts to a webhook.
- **Dump alerts:** `DumpsStreamController` long-polls the backend for time-sensitive
  alerts, surfaced in-client via `Notifier`.
- **Live current suggestion is in-memory only** (`SuggestionManager`) — not written to a
  documented file. Tapping it programmatically needs the backend API (unofficial,
  MessagePack) or screen-reading the panel — treat as [CONFIRM]/advanced (§3.7).
- **Pattern to replicate (in-bounds):** Copilot's `OfferHandler`/`OfferEditor` (pre-fill
  GE price/qty) and `HighlightController`/`WidgetHighlightOverlay` (outline slot/button)
  are the sanctioned Plugin-Hub behaviors. A "better Copilot" replicates and improves
  these; only the click/confirm stays manual (§0).

---

## 2. System Architecture

```
                 OSRS Wiki API (/latest /mapping /1h /timeseries)
                        |                         |
           [3.1 Price Watcher]          [3.2 History DB + Buy Scorer]
           buy-side signals  ---------->  backfill + score GOOD/OK/RISKY/AVOID
                        |                         |
   ~/.runelite/flipping/<user>.json               |
                        |                         |
           [3.3 Position Reader]                   |
           open positions + cost basis            |
           -> sell/hold advice                    |
                        \                         /
                         \                       /
                       [3.4 Notification / Delivery]
                  Windows toast | own-server Discord webhook | OpenClaw
                                |
                       [3.5 OpenClaw integration]
              launch/manage via system.run; chat control; blocklist edits
```

All components are local. Data flows one way: read public prices + the user's own
files → decide → notify. Nothing writes to the game.

**Plugin adapter layer.** Both plugins sit behind three interfaces so the rest of the
code is plugin-agnostic:
- `SignalSource` — where buy/sell ideas come from. `WikiMarginSource` (our engine, used
  standalone, for FU, and as an independent second opinion for Copilot) or
  `CopilotSuggestions` (Copilot's own picks; see §3.7 for access reality).
- `PositionSource` — what you hold + cost basis. `FlippingUtilitiesPositions` or
  `CopilotPositions` (§3.3).
- `BlocklistTarget` — where "don't suggest X" lives. Our `config.json` (standalone/FU)
  or Copilot's native `{profile}.profile.json` (§3.6).
Everything else (tax math, history scorer, delivery, OpenClaw wiring) is shared. The
active plugin is a config setting; adapters are selected at startup.

---

## 3. Components

### 3.1 Price Watcher (buy-side signal engine)
**Purpose:** poll prices, compute tax-adjusted margins, emit buy candidates.
**Inputs:** `/mapping` (once, cached), `/latest` (each cycle), `/1h` (every few min).
**Per-item evaluation (filters configurable):**
- `buy = low + undercut`, `sell = high - undercut` (undercut default 0).
- Reject if either price missing, if `sell <= buy`, or if `highTime`/`lowTime` older
  than `max_price_age_minutes` (stale = fake margin).
- `profit = sell - tax(sell) - buy`; reject if `< min_profit_per_item`.
- `roi = profit/buy*100`; reject if `< min_roi_pct`.
- Liquidity: hourly volume = `min(highPriceVolume, lowPriceVolume)` from `/1h`;
  reject if `< min_hourly_volume`. (See §6 volume note.)
- Respect `min_buy_price`/`max_buy_price` band.
- Skip anything on the blocklist.
**Output:** ranked list of opportunity dicts (see §4.2).
**Edge cases:** API 5xx/timeout → log and continue; items absent from `/mapping` →
skip; per-item buy `limit` may be `None` → show "?".

### 3.2 History DB + Buy Scorer
**Purpose:** give the agent context to judge good buy vs. trap, and accumulate a
timeline of every item ever flagged.
**Backfill-on-first-sight:** when an item is first flagged, pull
`/timeseries?timestep=24h&id=` (~365 pts) into SQLite. Sleep ~0.3s between backfills
to be polite on bursts.
**Accumulate:** log every fired signal to an `observations` table.
**Score (`GOOD/OK/RISKY/AVOID/UNKNOWN`) with human-readable reasons:**
- **Price percentile:** rank current `buy` within historical `avgLow` over the
  window. Low percentile (near historical lows) = good entry; high (≥ `buy_high_percentile`,
  default 0.85) = "buying high" → RISKY.
- **Margin anomaly (primary trap signal):** `ratio = current_margin / median_historical_margin`.
  `ratio ≥ margin_anomaly_ratio` (default 2.5) → AVOID ("likely a spike/thin/stale
  quote, not real profit"). `1.2–2.5` → healthy.
- **Volume health:** `current_volume / median_historical_volume`; below
  `thin_volume_ratio` (default 0.3) → RISKY ("may not fill"). **See §6.**
- **Trend:** slope of recent `avgLow`; down ≥ `downtrend_pct` (default 0.10) → RISKY.
- `< min_history_points` data → UNKNOWN (never fake a verdict).
- `suppress_avoid` (default true) drops AVOID-tier items from notifications.

### 3.3 Position Reader (sell-side) — `PositionSource` adapters
**Purpose:** know what the user holds and at what cost, and advise when to sell.
**Shared output** per item: `{net_qty, avg_cost_basis, time_held}`. Then cross-reference
`/latest`: `sell_now = high`; `net_per_item = sell_now - tax(sell_now) - cost_basis`;
advise SELL if profitable + liquid, HOLD if underwater. Always note how fresh the
underlying file is.

**Adapter A — Flipping Utilities** *(blocked on §1.3 CONFIRM; needs a real snippet)*
- File: `~/.runelite/flipping/<username>.json` → `AccountData.trades[]` →
  `FlippingItem.history` → `OfferEvent[]`.
- Normalize cumulative GE events to discrete fills; `net_qty = Σbuy.qty − Σsell.qty`;
  FIFO cost basis (weighted-average acceptable v1). **Do not write the parser until a
  real snippet is seen.**
- Freshness: written on logout/shutdown only → can be stale mid-session.

**Adapter B — Flipping Copilot** *(file names VERIFIED; CONFIRM exact fields)*
- Dir: `~/.runelite/flipping-copilot/`. Pure local JSON/JSONL reads — no new deps, no
  backend, no auth.
- **Open offers:** `acc_{accountHash}_{slot}.json` for slots 0–7, each a `SavedOffer`
  `{item id, price, quantity, state}`. Union across slots = current GE offers.
- **Recent fills:** `{displayNameSHA1}_un_acked.jsonl` — `Transaction` lines (dedupe by
  UUID) for completed buys/sells not yet synced.
- **Cost basis:** prefer a flip-history cache if present (`flips_{accountId}.json`
  **[CONFIRM]**); else reconstruct from transactions (FIFO as above).
- Selecting files: glob the dir, or compute `accountHash`/`SHA1(displayName)` from the
  user's account. Freshness: offer cache writes on change + shutdown (async) — fresher
  than FU's logout-only file.
- Copilot also computes its own sell suggestions server-side; this adapter is an
  *independent* read so OpenClaw can advise without the panel open.

### 3.4 Notification / Delivery
- Always append each alert to `alerts.jsonl` (audit + the OpenClaw-tail route).
- `notify_method`:
  - `"windows"` — direct Windows toast via `win11toast`; degrade to stdout if absent.
  - `"discord"` — POST an embed to a **user-owned** Discord **webhook** URL (clean,
    mobile-friendly). Rate-limit/debounce to avoid 429s.
  - `"openclaw"` — write only; the OpenClaw agent tails `alerts.jsonl` and calls
    `system.notify`. **[CONFIRM]** the exact invocation; until then prefer `windows`
    or `discord`.
- Each alert line should carry: item, buy, sell, profit/ea, ROI, buy limit, hourly
  volume, and the §3.2 verdict + top reason.

### 3.5 OpenClaw integration
- `~/.openclaw/openclaw.json` → `gateway.nodes.allowCommands` must include
  `"system.run"` (to launch/manage the watcher) and `"system.notify"` (only if using
  the OpenClaw toast route). Explicit names; no wildcards.
- The agent launches the watcher with `system.run` → `python <path>\ge_flip_watcher.py`.
- Conversational control maps to `system.run` of the CLI subcommands (§3.6): start/stop,
  "block X", "what do I hold", "should I sell X".
- OpenClaw delivers and controls; it doesn't perform the in-game click (§0).

### 3.6 Config & blocklist management
- `config.json` is re-read every cycle (live edits to thresholds/blocklist apply
  without restart).
- **`BlocklistTarget` depends on mode:**
  - *Standalone / FU:* our own `config.json` `blocklist` filters the Wiki engine.
  - *Copilot:* write to Copilot's **native** blocklist — the blocked-items field in
    `{profileName}.profile.json` under `~/.runelite/flipping-copilot/`. Copilot reloads
    it every ~5 s, so edits take effect live in the plugin itself. Mirror Copilot's
    write discipline (atomic write + `.lock`), and round-trip the rest of the file
    unchanged. **[CONFIRM the exact field/array name for blocked items.]**
- CLI subcommands (so the agent can run them via `system.run`):
  `block "<item>"`, `unblock "<item>"`, `list`, plus `--once` (single scan) and
  history tools `backfill "<item>"`, `score "<item>"`, `report`. `block`/`unblock`
  route to whichever `BlocklistTarget` is active.
- The agent may *suggest* blocks based on which items repeatedly score AVOID/RISKY.

### 3.7 Notification source by plugin (what you can actually ingest)
- **Standalone / FU:** FU has no clean alert feed (osrs.cloud is gated and JS-rendered;
  self-botting Discord is out, §0). Generate signals locally with the Wiki engine.
- **Copilot — options, cleanest first:**
  1. **Augment, don't ingest (recommended v1):** read Copilot's offer/transaction files
     (§3.3-B) for what you hold / just did, score with §3.2, deliver via OpenClaw. No
     auth, no fragile API.
  2. **Copilot → your own Discord webhook:** enable Copilot's native `WebHookController`
     to post session/flip summaries to a webhook *you* own; read that channel with a
     **bot token** in **your** server (never a user token — §0). Good for summaries, not
     per-suggestion buys.
  3. **Backend API / screen-read [CONFIRM/advanced]:** the live suggestion could come
     from `api.flippingcopilot.com` (reuse the JWT in `login-response.json`; MessagePack;
     unofficial and liable to break) or via OCR of the SuggestionPanel through OpenClaw
     `screen.snapshot`. Only if you truly need the live pick programmatically; budget for
     maintenance.

---

## 4. Data Models

### 4.1 `config.json` (authoritative; hot-reloaded)
```json
{
  "user_agent": "ge-flip-assistant - REPLACE_ME",
  "poll_seconds": 60,
  "volume_refresh_seconds": 300,
  "scan_all": true,
  "watchlist": [],
  "blocklist": ["Old school bond"],
  "filters": {
    "min_profit_per_item": 50, "min_roi_pct": 1.5, "min_hourly_volume": 200,
    "min_buy_price": 100, "max_buy_price": 50000000, "max_price_age_minutes": 30
  },
  "undercut": 0,
  "alert_cooldown_minutes": 30,
  "max_alerts_per_cycle": 3,
  "notify_method": "windows",
  "discord": { "webhook_url": "" },
  "openclaw": { "alerts_file": "alerts.jsonl" },
  "history": {
    "enabled": true, "db_path": "flip_history.db", "backfill_timestep": "24h",
    "score_window_points": 120, "min_history_points": 10, "suppress_avoid": true,
    "buy_high_percentile": 0.85, "buy_low_percentile": 0.35,
    "margin_anomaly_ratio": 2.5, "thin_volume_ratio": 0.3,
    "downtrend_pct": 0.10, "uptrend_pct": 0.10
  },
  "ge_tax": { "rate": 0.02, "per_item_cap": 5000000, "free_below": 50,
              "exempt_items": ["Old school bond"] }
}
```

### 4.2 Opportunity (in-memory)
`{id, name, buy, sell, tax, profit, roi, limit, volume_1h, max_profit_4h, verdict, verdict_reason}`

### 4.3 SQLite schema
- `items(id PK, name, buy_limit, members, first_seen, backfilled)`
- `price_history(item_id, ts, avg_high, avg_low, high_vol, low_vol, step, PRIMARY KEY(item_id, ts, step))`
- `observations(item_id, ts, buy, sell, margin, profit, roi, volume, verdict)`

---

## 5. Validated Reference Implementations

These were tested against the live API this session. Reuse or adapt.

**GE tax** (verified):
```python
def ge_tax(sell, name, cfg):
    if sell < cfg["free_below"]:
        return 0
    if name.lower() in {n.lower() for n in cfg.get("exempt_items", [])}:
        return 0
    return min(int(sell * cfg["rate"]), cfg["per_item_cap"])
```

**Buy scorer** (tested; verdicts were sensible on Magic logs / Abyssal whip / Nature
rune / Twisted bow). Percentile, margin-anomaly, volume, trend as in §3.2. See the
companion `flip_db.py` for a full working version.

**Backfill** via `/timeseries?timestep=24h&id=` returned ~365 daily points/item and
populated `price_history` cleanly.

> A complete, runnable starter (watcher + history DB + config + README) was produced
> alongside this spec as **reference** (`ge_flip_watcher.py`, `flip_db.py`,
> `config.json`, `README.md`). Treat it as a proven skeleton, not a finished product
> — it still needs the §6 fixes and the §3.3 position reader.

---

## 6. Known Issues / Must-Fix

1. **Volume unit mismatch (real bug).** The watcher's *current* volume comes from
   `/1h` (hourly), but the scorer's historical baseline comes from `/timeseries 24h`
   (daily). Comparing hourly-now to daily-median makes almost everything look "thin."
   **Fix:** make the comparison like-for-like — either also backfill
   `/timeseries?timestep=1h` and use its volume median as the baseline, or normalize
   (e.g. compare daily current volume from `/24h` to the daily historical median).
   Pick one and keep units consistent end-to-end.
2. **FU file staleness.** On-disk positions reflect the last logout/shutdown. Surface
   the file's last-modified time with sell advice; don't present stale holdings as live.
3. **OfferEvent normalization [CONFIRM].** GE offer events are cumulative; dedupe to
   discrete fills before computing positions. Validate against a real file.
4. **OpenClaw `system.notify` invocation [CONFIRM].** Verify how a script triggers it,
   or default to the `windows`/`discord` routes.

---

## 7. Build Phases & Acceptance Criteria

1. **Watcher core** — config load, API fetch, evaluate, ranked output.
   *Done when:* `--once` prints sane tax-adjusted opportunities against live data.
2. **History DB + scorer** — schema, backfill-on-first-sight, scoring, AVOID suppression.
   *Done when:* a flagged item gets ~365 backfilled points and a verdict with reasons;
   the §6.1 volume fix is in and verdicts aren't all "thin".
3. **Delivery** — Windows toast + own-server Discord webhook + `alerts.jsonl`; cooldown.
   *Done when:* a real flip produces one toast and one webhook post, deduped.
4. **OpenClaw wiring** — allowlist, `system.run` launch, CLI subcommands for chat control.
   *Done when:* the agent can start/stop the watcher and edit the blocklist by chat.
5. **Position readers (sell-side `PositionSource`)** — Copilot adapter can start as soon
   as the §8.3 file samples land (pure local reads); FU adapter waits on the §8.2 snippet.
   FIFO cost basis; sell/hold advice; staleness note.
   *Done when:* given the user's files, it lists held items, cost basis, and a correct
   sell/hold call cross-referenced to live prices, for whichever plugin is active.
6. **Polish** — robustness to API outages, optional FU-alert ingestion (§3.7) iff a
   clean webhook path exists.

---

## 8. Open Questions / Inputs Needed From the User

1. **Which plugin(s) are in use** — Flipping Utilities, Flipping Copilot, both, or
   standalone. Determines which adapters to build first. (User has said: build both.)
2. **If FU:** a real, redacted snippet of `~/.runelite/flipping/<username>.json` — one
   `trades[]` entry with its `history` (fuzz prices/quantities; keep structure + field
   names). **Blocks the FU position adapter.**
3. **If Copilot:** small redacted samples from `~/.runelite/flipping-copilot/` —
   (a) one `acc_{hash}_{slot}.json`, (b) one line of `{hash}_un_acked.jsonl`, (c) the
   blocked-items portion of `{profile}.profile.json`, and (d) whether a
   `flips_{accountId}.json` exists. **Confirms `SavedOffer`/`Transaction` field names,
   the blocklist field name, and the cost-basis source.**
4. **OpenClaw version + how it invokes node `system.notify`** (for the `openclaw` notify
   route). Otherwise default to `windows`/`discord`.
5. **Bankroll & preferences** to tune thresholds (min profit/ROI/volume, price band,
   members-only, watchlist vs. scan-all). For Copilot, also whether you want the live
   suggestion ingested (§3.7 option 3) or just augmentation (option 1).

---

## 9. Tech Stack & Setup
- Python 3.11+, `requests`, stdlib `sqlite3`. Optional `win11toast`, `discord.py`.
- OpenClaw Windows node with Node Mode enabled and the §3.5 allowlist.
- A user-owned Discord server + webhook (for the `discord` delivery route).
