# OSRS GE Flip Assistant — Developer Handoff Specification

**Audience:** a local Claude Code session that will implement this.
**Format of facts:** **[VERIFIED]** = confirmed against live sources this research session.
**[CONFIRM]** = validate locally (usually exact JSON field names) before relying on it.

---

## 0. What you're building — one product, two components

A flipping assistant that is **better than Flipping Copilot, up to (but not including)
the click**. It suggests, scores, pre-fills the GE offer, and highlights where to act;
the human performs the actual click/confirm.

It ships as **two components that talk to each other over localhost**:

| | Component A — RuneLite plugin | Component B — Companion service |
|---|---|---|
| Language | **Java 11** (RuneLite is Java) | **Python 3.11+** |
| Runs | inside the RuneLite client | as a local process + OpenClaw node |
| Job | in-client UX: suggestion panel, score overlay, GE **pre-fill**, slot/button **highlights** | the brain + reach: signal/scoring engine, history DB, plugin-file readers, phone/desktop/Discord delivery, voice control |
| Boundary | stops at the click | never actuates the game |

**Why two components:** only a RuneLite plugin (Java, in-client) can read live game
state and pre-fill/highlight the GE interface. Only an external service can run the
history database, push notifications to your phone, and be driven by OpenClaw. A can
work standalone; B can work standalone (notify-only); together they're the full product.

**How they talk:** Component B exposes a tiny **HTTP server on `127.0.0.1`** (loopback
only). A `GET`s suggestions/scores; optionally `POST`s offer events back. (A flat shared
JSON file is an acceptable v1 alternative.)

**The one hard line:** suggest, score, pre-fill, highlight = all fine (this is exactly
what Copilot ships and the Plugin Hub allows). Do **not** synthesize the click/keypress
that places or confirms an offer, and do not drive the client with pyautogui / AutoHotkey
/ Desktop Commander / Windows MCP / OpenClaw clickers. The human does that.

**Conventions:**
- No AI/assistant attribution or "Co-authored-by"/"Generated with" trailers in commits/PRs.
- Discord: if reading a channel, use a **bot** token in a server you own (not a user token).
- Component B: `requests`, stdlib `sqlite3`; optional `win11toast`, `discord.py`. One
  hot-reloaded `config.json`. No secrets in code.

---

## 1. Architecture at a glance

```
        OSRS Wiki API                      Flipping plugin files (the user's own data)
   /latest /mapping /1h /timeseries     ~/.runelite/flipping(-copilot)/...
            |                                         |
            v                                         v
   ┌─────────────────────────── COMPONENT B (Python) ───────────────────────────┐
   │  Signal+Scoring engine   History DB (SQLite)   Position readers (adapters)  │
   │        |                       |                         |                  │
   │        └───────── localhost HTTP (127.0.0.1) ────────────┘                  │
   │  Delivery: Windows toast | own-server Discord webhook | OpenClaw system.notify│
   │  Control:  OpenClaw system.run -> CLI (block X / what do I hold / report)    │
   └─────────────────────────────────┬──────────────────────────────────────────┘
                                      | localhost HTTP
   ┌──────────────────────────────────v─────────────── COMPONENT A (Java plugin) ┐
   │  Reads game state (inventory, offers, slots, gold) via RuneLite API          │
   │  Suggestion panel  •  GOOD/RISKY score overlay  •  GE price/qty PRE-FILL      │
   │  slot/button HIGHLIGHT  •  [human clicks to place/confirm]                    │
   └──────────────────────────────────────────────────────────────────────────────┘
```

Data flows one way into decisions; nothing writes to the game.

---

## 2. Component A — RuneLite plugin (Java)

### 2.1 Toolchain & frameworks
- **Java 11**, **Gradle**, **IntelliJ IDEA Community**.
- **RuneLite API** (provided by the client at runtime), **Guice** (DI, provided),
  **Lombok**, **Swing** (panels/overlays), **OkHttp** (provided — use it to call
  Component B). Distributed via the **RuneLite Plugin Hub**.
- This is the same stack Flipping Copilot uses (Java 11, Gradle, RuneLite API, Guice,
  Swing, OkHttp) — model on it.

### 2.2 Where the docs are (authoritative)
- **Developer Guide** (start here): `https://github.com/runelite/runelite/wiki/Developer-Guide`
  — covers `@PluginDescriptor`, `@Subscribe` events, config, overlays.
- **Example plugin template** (project skeleton): `https://github.com/runelite/example-plugin`
- **Plugin Hub info**: `https://github.com/runelite/runelite/wiki/Information-about-the-Plugin-Hub`
- **Plugin Hub submission repo** (how to publish; BSD-2 expected): `https://github.com/runelite/plugin-hub`
  — fork, add `plugins/<your-plugin>` with `repository=` and `commit=`, open a PR;
  RuneLite devs review for compliance with Jagex's 3rd-party rules.
- **API Javadoc** is linked from the Developer Guide; in practice the client source
  (`runelite/runelite`, modules `runelite-api` and `runelite-client`) is the reference.
- **Reference implementation to study/borrow from:** Flipping Copilot source
  `https://github.com/cbrewitt/flipping-copilot` (BSD-2 in parts — reusable under that
  license) and its architecture wiki `https://deepwiki.com/cbrewitt/flipping-copilot`.

### 2.3 How a RuneLite plugin works (essentials)
- Entry class `extends Plugin`, annotated `@PluginDescriptor`; lifecycle `startUp()` /
  `shutDown()`.
- `@Inject` RuneLite services: `Client`, `ClientThread`, `OverlayManager`, `ItemManager`,
  `ConfigManager`, `ClientToolbar` (nav button), etc.
- **`@Subscribe` event handlers** (the ones you need, all also used by Copilot):
  - `GrandExchangeOfferChanged` — a GE slot's offer state changed (buying/selling/filled).
  - `ItemContainerChanged` — inventory / bank changes (track gold & items).
  - `GameTick` — periodic work (poll Component B, refresh suggestions ~ every tick/600ms).
  - `GameStateChanged` — login/logout.
  - `WidgetLoaded` / `WidgetClosed` — GE interface open/close (know when to pre-fill/highlight).
  - `VarbitChanged` / `VarClientIntChanged` — game variables.
- **Thread rule:** all game API access happens on `ClientThread` (`clientThread.invoke`/
  `invokeLater`). UI is Swing (EDT). Don't block the game thread on HTTP — use OkHttp async.
- Config via a `Config` interface (`@ConfigGroup`). Overlays via `OverlayManager`.

### 2.4 What the plugin reads (live game state)
- Inventory & gold: `ItemContainer` (inventory id) via `Client`/`ItemContainerChanged`.
- Open GE offers & slots: `client.getGrandExchangeOffers()` + `GrandExchangeOfferChanged`.
- This is the state Component B's sell/score logic benefits from; A can forward it to B,
  or B can read the plugin-cache files (§4.3/§4.4) independently.

### 2.5 What the plugin does (in-client UX — all in-bounds)
- **Suggestion panel** (Swing `PluginPanel`): shows the next buy/sell from the engine (§3.2),
  with our score (§3.3) and reasons.
- **Score overlay**: GOOD/OK/RISKY/AVOID badge on the current item.
- **GE pre-fill**: when the GE offer screen is open for a suggested item, set the price and
  quantity input widgets. **Model on Copilot's `OfferHandler` + `ui/OfferEditor`.**
- **Highlight**: outline the GE slot / confirm button / inventory item to guide the user.
  **Model on Copilot's `HighlightController` + `WidgetHighlightOverlay`** (uses
  `OverlayManager` + widget bounds).
- **Stop there.** The user clicks to place/confirm.

### 2.6 Talking to Component B
- On `GameTick` (throttled) the plugin `GET http://127.0.0.1:<port>/suggestion?account=...`
  → `{action, item, price, qty, verdict, reason}` and renders it.
- Optionally `POST /event` with offer/fill updates so B's history/delivery stays live.
- Loopback only; no auth needed if bound to `127.0.0.1`. Degrade gracefully if B is down
  (plugin still works off its own engine or shows "companion offline").

---

## 3. Component B — Companion service (Python + OpenClaw)

### 3.1 Frameworks
- Python 3.11+, `requests`, stdlib `sqlite3`, `http.server` (or `flask`/`fastapi` if
  preferred) for the localhost API. Optional `win11toast`, `discord.py`. OpenClaw Windows
  node for phone/desktop reach + voice control.

### 3.2 Signal engine (buy-side) — the "better Copilot" brain
- Poll the Wiki API (§4.1); compute tax-adjusted margins (§4.2); filter by profit, ROI,
  hourly volume, price band, and price staleness. Output ranked opportunities.
- Serve the current best suggestion(s) to Component A over localhost.

### 3.3 History DB + scorer (buy-quality context)
- SQLite. **Backfill-on-first-sight** via `/timeseries?timestep=24h&id=` (~365 daily
  points instantly), then accumulate. Score GOOD/OK/RISKY/AVOID + reasons from: price
  percentile vs history, margin-anomaly ratio (primary trap signal), volume health, trend.
- This score is what A overlays and what suppresses junk.

### 3.4 Position readers (sell-side) — `PositionSource` adapters
Shared output per item `{net_qty, avg_cost_basis, time_held}`; cross-ref `/latest`
(`sell_now=high`), advise SELL if profitable+liquid else HOLD, note file freshness.
- **FU adapter** — `~/.runelite/flipping/<username>.json` (§4.4). **[blocked on a real snippet]**
- **Copilot adapter** — `~/.runelite/flipping-copilot/` files (§4.3); pure local reads.

### 3.5 Delivery + control
- Delivery: Windows toast (`win11toast`), **own-server Discord webhook**, or OpenClaw
  `system.notify`. Always append to `alerts.jsonl`. Cooldown/dedupe.
- Control: OpenClaw runs the watcher via `system.run`; CLI subcommands map to chat:
  `block "<item>"`, `unblock`, `list`, `--once`, `backfill`, `score`, `report`.
- OpenClaw allowlist (`~/.openclaw/openclaw.json` → `gateway.nodes.allowCommands`):
  `"system.run"`, and `"system.notify"` if using that toast route (explicit names; no
  wildcards). OpenClaw delivers and controls; it doesn't perform the in-game click.

### 3.6 Blocklist target (depends on active plugin)
- **Standalone / FU:** our `config.json` `blocklist` filters the engine.
- **Copilot:** write Copilot's **native** blocked-items list in `{profile}.profile.json`
  (§4.3) — Copilot reloads it every ~5 s, so edits apply live in the plugin. Atomic write
  + `.lock`, round-trip the rest unchanged. **[CONFIRM the blocked-items field name.]**

---

## 4. Data sources — where to source everything

### 4.1 OSRS Wiki Real-time Prices API **[VERIFIED]**
- Base: `https://prices.runescape.wiki/api/v1/osrs`. **Descriptive User-Agent required**
  (blocks default/library UAs). Built from **completed RuneLite trades only** (lags slightly).
- `GET /mapping` → `[{id, name, members, limit, value, lowalch, highalch, examine, icon}]`
  (`limit` = 4-hour buy limit; ~4,500 items; cache once).
- `GET /latest` → `{"data":{"<id>":{high, highTime, low, lowTime}}}`. **`high`=instabuy
  (your sell target), `low`=instasell (your buy target); flip = buy≈low, sell≈high.**
- `GET /1h` `/5m` `/24h` → `{avgHighPrice, avgLowPrice, highPriceVolume, lowPriceVolume}`.
- `GET /timeseries?timestep={5m|1h|6h|24h}&id={id}` → up to ~300 points; `24h` ≈ 365 daily.

### 4.2 Grand Exchange tax **[VERIFIED]**
- 2% of the **sell** price, **floored per item**, **capped at 5,000,000 gp/item**; items
  under 50 gp pay 0; bonds + a small list exempt; buyer pays no tax.
- `tax(sell) = 0 if (exempt or sell<50) else min(floor(sell*0.02), 5_000_000)`;
  `profit = sell - tax(sell) - buy`. Verified: 1250→25, 49→0, 300M→5M, bond→0.

### 4.3 Flipping Copilot — what you get and from where **[architecture VERIFIED; fields CONFIRM]**
- Repo `cbrewitt/flipping-copilot` (v1.7.20, Java 11). Suggestions are **server-side** from
  `api.flippingcopilot.com` (JWT auth, **MessagePack** payloads) — reading that backend
  directly is unofficial/fragile and not needed for v1.
- **Local files dir:** `~/.runelite/flipping-copilot/` (`RUNELITE_DIR/flipping-copilot/`):
  - `login-response.json` — JWT token, user id, **premium status**.
  - `acc_{accountHash}_{slot}.json` — `SavedOffer` per GE slot 0–7: **item id, price,
    quantity, state**. Union of slots = your current open offers. (`accountHash =
    client.getAccountHash()`.)
  - `{displayNameSHA1}_un_acked.jsonl` — completed `Transaction`s not yet backend-synced,
    one JSON per line, **deduped by UUID** = your buy/sell fills.
  - `{displayNameSHA1}_session_data.jsonl` — `SessionData`: `startTime`(int, unix s),
    `durationMillis`(long), `averageCash`(long).
  - `{profileName}.profile.json` — preferences incl. **blocked items** + risk settings;
    atomic writes w/ `.lock`; **reloaded every ~5 s** (external edits apply live).
  - `flips_{accountId}.json` — local cache of completed flip history (cost basis) **[CONFIRM exists]**.
  - Exact JSON field names of `SavedOffer` / `Transaction` / blocked-items array = **[CONFIRM]**
    against real files (see §8).
- **Webhook:** Copilot's `WebHookController` posts a **standard Discord webhook message
  (embed)** with **session stats + flip summaries** (built from `SessionData` + profit
  tracking). To ingest it: point Copilot's webhook at a channel in **your own** server, read
  it with a **bot token**. Exact embed fields = **[CONFIRM via `WebHookController.java`]**.
  Good for summaries, not per-suggestion buys.
- **Dump alerts:** `DumpsStreamController` long-polls the backend; surfaced in-client via
  `Notifier`. **Live current suggestion is in-memory only** (`SuggestionManager`) — not on
  disk; tapping it needs the backend API or screen-reading (advanced).
- **Pattern to replicate (in-bounds):** `OfferHandler`/`OfferEditor` (pre-fill) and
  `HighlightController`/`WidgetHighlightOverlay` (highlight) — see §2.5.

### 4.4 Flipping Utilities — what you get and from where **[location/nesting VERIFIED; fields CONFIRM]**
- Repo `Flipping-Utilities/rl-plugin`. It's a tracker (no buy-suggestion engine — our engine
  supplies signals for FU users).
- **File:** `~/.runelite/flipping/<account_username>.json` = an `AccountData` object:
  `AccountData.trades` → `List<FlippingItem>`; each `FlippingItem.history` (a
  `HistoryManager`) → list of `OfferEvent` with **price, quantity, buy/sell flag, timestamp**.
- **Written on logout / client shutdown** → can be stale mid-session. `GrandExchangeOfferChanged`
  events are cumulative, so `OfferEvent`s may need de-duping into discrete fills.
- Exact JSON field names = **[CONFIRM via a real redacted snippet]** (see §8). osrs.cloud /
  the Flopper Discord bot is gated + JS-rendered — not a clean API.

### 4.5 OpenClaw Windows node **[VERIFIED; notify-from-script CONFIRM]**
- Node Mode lets the agent drive the PC via allowlisted capabilities: `system.notify`
  (toast), `system.run` (command), `screen.snapshot`, `tts.speak`, `canvas.*`. Gated by
  `gateway.nodes.allowCommands` in `~/.openclaw/openclaw.json` (explicit names) + gateway
  pairing. **No native mouse/keyboard input primitive.** Exact way for a *script* to trigger
  `system.notify` = **[CONFIRM]**; default to the `windows`/`discord` routes meanwhile.

---

## 5. Data Models

### 5.1 `config.json` (Component B; hot-reloaded)
```json
{
  "active_plugin": "copilot",            // "copilot" | "flipping_utilities" | "standalone"
  "user_agent": "ge-flip-assistant - REPLACE_ME",
  "localhost_port": 8765,
  "poll_seconds": 60,
  "scan_all": true, "watchlist": [], "blocklist": ["Old school bond"],
  "filters": { "min_profit_per_item": 50, "min_roi_pct": 1.5, "min_hourly_volume": 200,
    "min_buy_price": 100, "max_buy_price": 50000000, "max_price_age_minutes": 30 },
  "undercut": 0, "alert_cooldown_minutes": 30, "max_alerts_per_cycle": 3,
  "notify_method": "windows", "discord": { "webhook_url": "" },
  "openclaw": { "alerts_file": "alerts.jsonl" },
  "history": { "enabled": true, "db_path": "flip_history.db", "backfill_timestep": "24h",
    "score_window_points": 120, "min_history_points": 10, "suppress_avoid": true,
    "buy_high_percentile": 0.85, "buy_low_percentile": 0.35,
    "margin_anomaly_ratio": 2.5, "thin_volume_ratio": 0.3, "downtrend_pct": 0.10 },
  "ge_tax": { "rate": 0.02, "per_item_cap": 5000000, "free_below": 50,
    "exempt_items": ["Old school bond"] }
}
```
### 5.2 Localhost API (B → A)
`GET /suggestion?account={hash}` → `{action:"buy|sell|wait", id, name, price, qty, verdict,
reason}`. `GET /score?id={id}&buy={n}&sell={n}` → `{verdict, reasons[]}`. `POST /event` ← A.

### 5.3 SQLite (Component B)
- `items(id PK, name, buy_limit, members, first_seen, backfilled)`
- `price_history(item_id, ts, avg_high, avg_low, high_vol, low_vol, step, PK(item_id,ts,step))`
- `observations(item_id, ts, buy, sell, margin, profit, roi, volume, verdict)`

---

## 6. Known Issues / Must-Fix
1. **Volume unit mismatch (real bug).** Current volume from `/1h` (hourly) vs historical
   baseline from `/timeseries 24h` (daily) makes everything look "thin." Fix: backfill a
   `/timeseries timestep=1h` baseline, or compare daily-to-daily via `/24h`. Keep units
   consistent.
2. **Plugin-file staleness.** FU file writes on logout/shutdown; Copilot offer cache writes
   on change+shutdown (fresher). Always surface file mtime with sell advice.
3. **Field-name confirmation.** FU `OfferEvent` and Copilot `SavedOffer`/`Transaction`/
   blocked-items names are [CONFIRM] — don't ship parsers built on guesses (see §8).
4. **OpenClaw `system.notify` from a script** [CONFIRM]; default to `windows`/`discord`.

---

## 7. Build Phases & Acceptance Criteria
1. **B: engine core** — Wiki fetch, tax-adjusted ranked opportunities. *Done:* `--once` prints
   sane opportunities live.
2. **B: history DB + scorer** — backfill-on-first-sight, scoring, AVOID suppression, §6.1 fix.
   *Done:* flagged item gets ~365 points + a verdict with reasons; verdicts aren't all "thin."
3. **B: delivery + control** — toast/own-server webhook/`alerts.jsonl`; OpenClaw `system.run`
   launch + CLI chat control. *Done:* a real flip toasts once and the agent can block an item by chat.
4. **B: position readers** — Copilot adapter when §8 files land (pure local reads); FU adapter
   when its snippet lands. *Done:* lists held items, cost basis, correct SELL/HOLD vs live price.
5. **A: plugin skeleton** — example-plugin template, panel + nav button, reads inventory/offers,
   calls B over localhost. *Done:* panel shows B's current suggestion in-client.
6. **A: pre-fill + highlight** — model on Copilot's OfferEditor/HighlightController; score overlay.
   *Done:* opening a suggested item's GE offer pre-fills price/qty and highlights the slot/button;
   the user clicks. Nothing auto-clicks.
7. **Polish** — outage robustness, profile/account selection, Plugin Hub submission.

---

## 8. Inputs Needed From the User
1. **Which plugin(s):** Copilot, Flipping Utilities, both, or standalone. (User: build both.)
2. **If Copilot** — redacted samples from `~/.runelite/flipping-copilot/`: one
   `acc_{hash}_{slot}.json`, one line of `{hash}_un_acked.jsonl`, the blocked-items chunk of
   `{profile}.profile.json`, and whether `flips_{accountId}.json` exists. Confirms
   `SavedOffer`/`Transaction`/blocklist field names + cost-basis source.
3. **If FU** — one redacted `trades[]` entry (with its `history`) from
   `~/.runelite/flipping/<username>.json`. Confirms `OfferEvent` field names.
4. **OpenClaw version** + how it invokes node `system.notify` (else default windows/discord).
5. **Bankroll & thresholds** (min profit/ROI/volume, price band, members-only, watchlist vs scan-all).

---

## 9. Validated Reference Code (Component B)
Tested against the live API this session.
```python
def ge_tax(sell, name, cfg):
    if sell < cfg["free_below"]: return 0
    if name.lower() in {n.lower() for n in cfg.get("exempt_items", [])}: return 0
    return min(int(sell * cfg["rate"]), cfg["per_item_cap"])
```
- **Scorer** (price percentile + margin-anomaly + volume + trend) and **backfill** via
  `/timeseries?timestep=24h&id=` (returned ~365 pts/item) were tested and produced sensible
  GOOD/RISKY verdicts. A runnable starter (`ge_flip_watcher.py`, `flip_db.py`, `config.json`,
  `README.md`) was produced alongside this spec as a proven Component-B skeleton.

## 10. Tech Stack Summary
- **Component A:** Java 11, Gradle, IntelliJ; RuneLite API + Guice + Swing + OkHttp; Plugin Hub.
- **Component B:** Python 3.11+, `requests`, stdlib `sqlite3`/`http.server`; optional
  `win11toast`, `discord.py`; OpenClaw Windows node.
