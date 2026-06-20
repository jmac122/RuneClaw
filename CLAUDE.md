# CLAUDE.md — RuneClaw

Instructions for Claude Code working in this repository.

## Project

**RuneClaw** is an OSRS Grand Exchange flipping assistant: suggest flips, score entry
quality, notify, and optionally place offers via an external click actuator.

**Canonical specification:** `HANDOFF_ge_flip_assistant.md` — read it before implementing
anything non-trivial. It is the source of truth for architecture, APIs, data shapes, build
phases, and acceptance criteria.

| Component | Path | Stack |
|-----------|------|-------|
| **B — Companion** | `companion/` | Python 3.11+, `requests`, stdlib `sqlite3`, optional `win11toast` / `discord.py` / `pyautogui` |
| **A — RuneLite plugin** | `plugin/` | Java 11, Gradle, RuneLite API, Guice, Swing, OkHttp |

Components talk over **loopback HTTP** (`127.0.0.1` only). No secrets in code; config lives
in hot-reloaded `companion/config.json`.

---

## How to work in this repo

1. **Read the handoff** — especially §0 (architecture), the section you are implementing,
   and §6 (known bugs to avoid).
2. **One build phase per task** unless the user explicitly widens scope. Phases and done
   criteria are in handoff **§7**.
3. **Propose a short plan** (files to add/change, how to verify) before large edits.
4. **Verify before claiming done** — run commands, show output or errors. Do not mark a
   phase complete on theory alone.
5. **Minimal diffs** — solve the requested phase only; no drive-by refactors or speculative
   features.
6. **Commits** — only when the user asks. No `Co-authored-by`, `Generated with`, or other
   AI attribution in commits or PRs.

### Handoff fact labels

- **[VERIFIED]** — treat as correct; do not re-research or contradict.
- **[CONFIRM]** — field names or integration details not yet validated locally. Stub with
  clear `TODO`/`NotImplementedError`; **never guess** Copilot or Flipping Utilities JSON
  schemas. Wait for user-provided redacted samples (handoff §8).

---

## Repository layout

```
RuneClaw/
  CLAUDE.md                      ← you are here
  HANDOFF_ge_flip_assistant.md   ← canonical spec
  prompts/phase-01.md            ← copy-paste prompts per build phase
  docs/USER_CONFIG.md            ← your local decisions (§8)
  companion/                     ← Component B (Python)
    ge_flip_watcher.py           ← main watcher + CLI
    flip_db.py                   ← SQLite + scorer
    execution_orchestrator.py    ← post-notify pipeline
    ge_flip_actuator.py          ← pyautogui click actuator
    config.json
    requirements.txt
  plugin/                        ← Component A (Java / RuneLite)
```

Create directories as needed. Keep Component A and Component B decoupled except via the
documented localhost API (handoff §5.2).

---

## Build order (handoff §7)

Work in this order unless the user directs otherwise:

| Phase | Focus |
|-------|--------|
| 1 | B: Wiki fetch, tax, filters, `--once` |
| 2 | B: SQLite, scorer, §6.1 volume fix |
| 3 | B: Delivery, `execution.mode`, pending queue, HTTP `/execute` |
| 4 | B: `ge_flip_actuator.py` (start with `dry_run: true`) |
| 5 | B: Position readers (blocked until §8 JSON samples exist) |
| 6 | A: Plugin skeleton, panel, poll `/suggestion` |
| 7 | A: Pre-fill, highlight, `GET /ge-state` |
| 8 | A + B: Full notify → execute → fill → sell loop |
| 9 | Polish, README, Plugin Hub prep |

---

## Coding principles (mandatory)

Apply **SOLID**, **DRY**, **KISS**, and **YAGNI** on every change.

### SOLID

- **Single responsibility** — one module, one reason to change.
  - `ge_flip_watcher.py` orchestrates; it does not embed SQL, scoring math, or click logic.
  - Separate: API client, tax calculator, scorer, notifier, orchestrator, actuator.
- **Open/closed** — extend via adapters (e.g. `PositionSource` for Copilot vs FU), not by
  editing core loops for each plugin.
- **Liskov** — adapter implementations honor the same contracts; callers must not need
  `instanceof` checks for correctness.
- **Interface segregation** — small interfaces (`SignalSource`, `PositionSource`,
  `BlocklistTarget`); no fat “god” service interfaces.
- **Dependency inversion** — depend on abstractions; inject config paths, DB, HTTP clients,
  and notifiers. Avoid hard-coded globals and module-level side effects at import time.

### DRY

- One definition for GE tax, verdict enums, config keys, and API response parsing.
- Shared constants for Wiki base URL, default thresholds, and execution statuses.
- Do not copy-paste filter logic between CLI, HTTP handlers, and the watcher loop.

### KISS

- Prefer stdlib (`sqlite3`, `http.server` or a single lightweight framework) over heavy
  frameworks unless the user requests otherwise.
- Straight-line control flow over clever metaprogramming.
- Explicit CLI subcommands over magic string dispatch.

### YAGNI

- Do not build abstractions “for later.” Extract on the **third** repetition, not the first.
- Do not implement Copilot/FU parsers until real JSON samples exist.
- Do not add Plugin Hub packaging until the plugin actually runs in-client.

---

## Python (`companion/`)

- **Python 3.11+**; type hints on public functions and dataclasses for config/DTOs.
- **Imports at top of file** — no inline imports unless breaking a documented circular
  dependency (comment why).
- **Config** — load from `config.json`; re-read each cycle where the handoff requires
  hot-reload. Never commit API keys, Discord tokens, or webhook URLs.
- **HTTP** — descriptive Wiki `User-Agent` (handoff §4.1). Handle 5xx/timeouts gracefully;
  log and continue.
- **SQLite** — parameterized queries only. Migrations or schema in one place (`flip_db.py`).
- **Subprocess actuator** — run `ge_flip_actuator.py` in a subprocess; do not block the
  watcher loop. Capture stdout/stderr for failures.
- **CLI** — use `argparse` subcommands matching handoff §3.5 (`--once`, `execute`,
  `pending`, `block`, etc.).

### Python structure target

```
companion/
  ge_flip_watcher.py      # entry + CLI + poll loop
  flip_db.py              # schema, backfill, observations
  scoring.py              # GOOD/OK/RISKY/AVOID (or inside flip_db if tiny)
  wiki_client.py          # /mapping, /latest, /1h, /timeseries
  tax.py                  # ge_tax()
  delivery.py             # toast, discord, alerts.jsonl
  execution_orchestrator.py
  ge_flip_actuator.py
  config.py               # load + validate config.json
  models.py               # shared dataclasses / types
```

Split files when a module exceeds ~300 lines or mixes concerns.

---

## Java (`plugin/`)

- **Java 11**, **Gradle**, model on [runelite/example-plugin](https://github.com/runelite/example-plugin)
  and Flipping Copilot patterns cited in the handoff.
- **RuneLite thread rule** — all `Client` / game API access on `ClientThread`
  (`clientThread.invoke` / `invokeLater`). Never block the game thread on HTTP; use OkHttp
  async callbacks.
- **UI** — Swing on EDT; overlays via `OverlayManager`.
- **GE state** — expose `GET /ge-state` on loopback (handoff §2.6); canvas-relative widget
  bounds, refreshed on `WidgetLoaded`, `GrandExchangeOfferChanged`, throttled `GameTick`.
- **Pre-fill** — set widget text on `ClientThread`; do not synthesize OS-level clicks from
  the plugin (clicks are the Python actuator’s job).

---

## Error handling & reliability

- Fail fast with **actionable messages** (missing config key, RuneLite window not found,
  stale `/ge-state`).
- **Idempotent** delivery where possible — cooldown + dedupe (handoff §3.5).
- **Actuator** — respect `dry_run`, `screenshot_on_failure`, rate limits. Re-fetch
  `/ge-state` immediately before each click burst (handoff §6.5).
- **Never fake data** — if history is insufficient, verdict is `UNKNOWN`, not `GOOD`.

---

## Testing & verification

There is no CI yet. Prove behavior by running:

```bash
# Phase 1+
cd companion && pip install -r requirements.txt
python ge_flip_watcher.py --once

# Phase 2+
python ge_flip_watcher.py score "Abyssal whip"
python ge_flip_watcher.py backfill "Abyssal whip"

# Phase 3+
python ge_flip_watcher.py pending
python ge_flip_watcher.py execute <action_id>

# Phase 4 (RuneLite open, dry_run first)
python ge_flip_actuator.py --action place_buy --dry-run ...
```

For Java: `./gradlew build` in `plugin/` once the project exists.

Add focused unit tests only when they cover real logic (tax, scorer edge cases, config
parsing) — not trivial getters or framework boilerplate.

---

## Security & config

- Bind HTTP servers to **`127.0.0.1`** only.
- Discord: **bot token** in a server you own — never user/self-bot tokens.
- `config.json` may contain empty placeholders for secrets; document env vars or local
  overrides in README, not in git.
- Do not log tokens or full webhook URLs.

---

## Git

- Do not commit unless the user asks.
- Do not amend pushed commits unless the user explicitly requests it.
- Keep commit messages imperative and focused on **why** (`Add wiki client with bulk fetch`,
  not `Update files`).

---

## Common mistakes to avoid

- Guessing Flipping Copilot / Flipping Utilities on-disk JSON field names.
- Comparing hourly volume to daily baselines (handoff §6.1 — real bug).
- Putting actuator click logic inside the RuneLite plugin.
- Blocking the game thread or the watcher loop on I/O.
- Scope creep across build phases in a single session.
- Over-engineering: factories, plugins-for-plugins, or config-driven strategy maps before
  there are two real implementations.

---

## When stuck

1. Re-read the relevant handoff section.
2. State what is blocked (missing sample file, RuneLite not running, API error).
3. Ask the user for §8 inputs rather than inventing schema or thresholds.
4. Prefer a working narrow slice over a partial full system.
