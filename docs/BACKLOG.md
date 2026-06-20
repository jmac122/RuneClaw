# Feature backlog (deferred requests)

Running list of user-requested features captured for later phases. These are **not**
in the active build phase; they are recorded here so they are not lost. Each item notes
the owning component, the relevant handoff section, and the likely build phase (handoff §7).

Reference UX comes from Flipping Copilot screenshots provided by the user — model the look
and behavior on those, but the data and logic are ours.

---

## 1. Configurable data timeframe + refresh rate

**Component:** B (engine/config) + A (UI buttons) · **Handoff:** §3.2, §5.1 · **Phase:** 2 (engine) → later (UI)

- Expose a **timeframe** selector that picks the data window driving the flip algorithm:
  **`5m`, `30m`, `1h`, `2h`, `8h`**. Modeled on Copilot's "How often do you adjust offers?"
  buttons (`5m / 30m / 2h / 8h / …`); we add `1h`.
- Expose the **refresh rate** (re-scan / re-suggest cadence) as a user option. We already have
  `config.poll_seconds`; surface it in config + UI. Note this is a *separate* knob from the
  data timeframe (Copilot couples them under one button; we keep scan cadence and data window
  independent).

**⚠ Key constraint to resolve before implementing — Wiki API timeframes are not arbitrary.**
The OSRS Wiki API only natively provides aggregates for **`/5m`, `/1h`, `/24h`** (and
`/timeseries` timesteps `5m | 1h | 6h | 24h`). **`30m`, `2h`, and `8h` have no native bulk
endpoint** and must be derived. Options (decide with the user):
- **Scale from `/1h` bulk** — estimate the window from the hourly rate (e.g. `8h ≈ 8 × /1h`
  volume). One bulk call; works for a full-market scan; approximate.
- **Aggregate `/timeseries` per item** — exact, but ~one call per item, so only viable for a
  watchlist, not a 4,500-item scan.
- **Snap to nearest native window** (`5m / 1h / 24h`) — simplest, least precise.
- Keep volume **units consistent** when comparing windows (handoff §6.1 — real bug).

---

## 2. GE price-history graph overlay (in-client)

**Component:** A (RuneLite plugin) · **Handoff:** §2.5 · **Phase:** 7

On the Grand Exchange **"Set up offer"** screen, render an overlay graph at the bottom of the
client showing recent price history for the item being offered:

- Range tabs: **`1d / 1w / 1m / 1y`**.
- Two price series: **instabuy** and **instasell** (red / green lines), with a header readout
  (`Instabuy: <price> | <age>`, `Instasell: <price> | <age>`).
- A dashed **"Your offer"** horizontal line at the offer price so the user sees where their
  price sits relative to the market band. **Live-linked to the *Price per item* input:** the
  line tracks the value currently typed in the offer screen and moves up/down on the y-axis as
  the user edits the price (before confirm), not just the already-placed offer. Read the price
  widget on `ClientThread` and redraw the overlay line on change.
- Source data from the Wiki `/timeseries` endpoint (per item) via Component B, or directly
  from the plugin — decide during Phase 7.

---

## 3. Transparent GE hover tooltip (in-client)

**Component:** A (RuneLite plugin) · **Handoff:** §2.5 · **Phase:** 7

When hovering a **listed GE offer slot**, show a transparent tooltip with live decision context:

- **Competitiveness banner** — e.g. `Sell offer is not competitive` with a suggested fix
  (`Set price to <= 1,371`).
- Fields: **Offer Price**, **State** (e.g. `OUT_OF_RANGE`), **Wiki Insta Buy**, **Wiki Insta
  Sell**, **Buy Age**, **Sell Age**, **Profit**.
- Optionally embed the same mini price-history graph from item #2 below the fields.
- This is the in-client surface for our GOOD/OK/RISKY/AVOID scorer (handoff §3.3) — wire the
  score + reasons into this tooltip once the scorer exists.

---

## 4. Quick-price popup on the "…" price-editor button (in-client)

**Component:** A (RuneLite plugin) · **Handoff:** §2.5 (pre-fill / `OfferEditor`), §3.4 (cost basis) · **Phase:** 7

When the user clicks the **"…"** (3-dot) button in *Price per item* on the GE offer screen,
show a text popup with clickable quick-set actions and tracking status. From the Copilot
reference, contents to replicate (mapped to **our** data, not Copilot's):

- **Cost-basis status line** — e.g. `no buy tracked`, or show the tracked avg buy price when we
  have it. Source from the position readers (handoff §3.4 `PositionSource` → `avg_cost_basis`).
- **`set to wiki insta buy: <price> gp`** — one-click set the offer to the Wiki instabuy/instasell.
- **`set to <RuneClaw> suggested price: <price> gp`** — one-click set to **our engine's** suggested
  buy/sell (the analog of Copilot's "set to Copilot price"). This is our suggestion, not Copilot's.
- **`Set a price for each item:`** — editable manual price (shows current value, e.g. `44774*`).
- **Link to price-editor hotkeys** — keyboard shortcuts for nudging the price for finer control.

Clicking an action pre-fills the price widget on `ClientThread` (same path as §2.5 pre-fill) and,
if the live "Your offer" graph line (item #2) is present, the line moves to the new price.

---

## 5. Hosted backend / web database (architecture track)

**Component:** B (deployment) + A (remote API client) · **Handoff:** §0, §3.2/§3.3, §5.3 · **Phase:** v2 — **promote to hosted at launch** (local SQLite is the store until then; user decision 2026-06-20)

Lift the local Component B into a hosted service so every plugin install pulls scores/history
from us — the Copilot distribution model — instead of each user running a local Python companion.
**Until launch, everything stays local** (loopback `sqlite3` at `companion/flip_history.db`).

**Premise correction (so we build the right thing):** the crowd-sourced *price* data is already
centralized — it's the **OSRS Wiki Real-time Prices API** (`prices.runescape.wiki`, handoff §4.1).
We consume it; we do not rebuild it. Copilot's backend serves *server-side suggestions* + *account
sync* (§4.3); Flipping Utilities is a *local tracker* + Wiki (§4.4). So our web DB's value is **not**
"let people pull prices" — it is:

1. **Denser/longer history than the Wiki exposes** — Wiki `/timeseries` caps ~300 points/step; a
   continuous `/5m` poller retains far denser history, which makes the 30m/2h/8h derived timeframes
   (item #1) precise for all users from day one.
2. **Server-side scoring** — run the engine/scorer once centrally, serve verdicts to all plugins.
   Also kinder to the Wiki API: one well-behaved poller (descriptive User-Agent) vs N clients.
3. **Distribution** — a Plugin-Hub Java plugin calls our hosted API; **no local Python** required.

**Design guardrail — global vs. private data:**
- **Global (safe to centralize):** `price_history`, `items`, computed scores/verdicts. Same for
  everyone; no privacy concern.
- **Private (per-user):** account positions, cost basis, flip history from Copilot/FU files. Stays
  **local**, or **opt-in authenticated sync only** — never silently uploaded (handoff §0 loopback /
  no-secrets stance).

**Compatibility:** the local engine is the server's brain — `rank_opportunities` and the
`flip_db.py` schema (`items` / `price_history` / `observations`) run identically local or hosted.
Build local first (Phases 1–2), then deploy; not a rewrite.

**Secret-sauce / IP boundary (firm rule):** the scoring + ranking algorithm is the product's
secret sauce and **must stay server-side** — Plugin Hub requires submitting Component A's full
source under BSD-2 (handoff §2.2), so anything in the plugin is *published source*. Therefore:
- **Component A = thin client:** game I/O + render only. **Zero scoring logic.**
- **Component B = brain:** engine/scorer/ranking, never shipped.
- `/suggestion` and `/score` responses carry **results only** (`{action, price, qty, verdict,
  reason}`) — **never** the thresholds/weights/percentiles that produced them. Those stay in
  server config (`buy_high_percentile`, `margin_anomaly_ratio`, …).
- Caveat: this protects the *code*, not the *behavior* — outputs are observable, so the algorithm
  is approximable via model extraction (same as Copilot). Acceptable; code-secret >> public source.
- **Build/iterate locally** until launch (tight loop); the same Component B code lifts into the
  hosted service unchanged. Local is the dev environment, server-side is the end goal.

**Decisions to make before building:** hosting + stack; public **read** API shape + auth +
rate-limiting/abuse prevention; whether private account sync is in scope; ongoing cost; how
Component A switches between localhost companion and the remote endpoint.

---

_Add new deferred requests above this line with: component, handoff section, target phase, and
enough detail to implement without re-asking._
