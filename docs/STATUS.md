# RuneClaw — current status & next session

_Last updated: 2026-06-20. Read this first when resuming; then `CLAUDE.md` and
`HANDOFF_ge_flip_assistant.md`._

## Agreed plan (user, 2026-06-20)

**Finish Component A (RuneLite plugin) UI/UX first, then return to the rest of Component B.**

## Done & pushed to `origin/main`

| Commit | What |
|---|---|
| `289a5d4` | Phase 1 — engine: Wiki client + tax-adjusted ranked opportunities |
| `30f27d3` | Deferred-feature backlog (`docs/BACKLOG.md`) |
| `87535ab` | Phase 2 — history DB (`flip_db.py`) + GOOD/OK/RISKY/AVOID scorer (`scoring.py`), §6.1 fix |
| `345701c` | Phase 3 — delivery (`delivery.py`) + execution orchestration (`execution_orchestrator.py`) + loopback HTTP (`server.py`) |
| `fe0af87` | Component A: RuneLite plugin + **live `/ge-state`** (verified in-client) |

Component B (Python) is through **Phases 1–3**; 42 tests green.
Component A (Java) has the **plugin skeleton + `/ge-state`** done and live-verified.

## Next up — Component A UI/UX (handoff §2.5)

Build the in-client UX on top of the existing plugin (`plugin/`). Order is flexible; suggested:

1. **Suggestion panel** (Swing `PluginPanel` + nav button) — poll Component B
   `GET http://127.0.0.1:8765/suggestion` and render the current buy/sell + verdict + reasons.
   _Note: B does not serve `/suggestion` yet — only orchestration endpoints exist. Either add it
   to `companion/server.py` first, or stub the panel against a fixture._
2. **Score overlay** — GOOD/OK/RISKY/AVOID badge on the current item (`OverlayManager`).
3. **GE pre-fill** — set price/qty widgets on `ClientThread`. Model on Copilot's
   `OfferHandler` / `ui/OfferEditor` (handoff §2.5). Entry is via the chatbox numeric input
   (`ComponentID.CHATBOX_FULL_INPUT`).
4. **Highlight** — outline the GE slot / confirm button / inventory item. Model on Copilot's
   `HighlightController` / `WidgetHighlightOverlay` (uses `OverlayManager` + the widget bounds
   we already resolve in `GeStateService`).
5. **Backlog UX** (`docs/BACKLOG.md`): #2 GE price-history graph overlay (live "Your offer"
   line), #3 transparent hover tooltip, #4 "…" quick-price popup.

## Then — remaining Component B (handoff §7)

- **Phase 4** — `ge_flip_actuator.py` (pyautogui). NOW UNBLOCKED: build it against the verified
  `/ge-state` shape (slots, `confirm_button`, `client_bounds`), `dry_run`-first, re-fetching
  `/ge-state` immediately before each click burst (§6.5). The orchestrator already invokes it.
- **Phase 5** — position readers. User runs **Flipping Copilot (account user=27802)** in-client,
  so Copilot adapter is viable once they provide redacted `~/.runelite/flipping-copilot/` samples
  (handoff §8). Do NOT guess Copilot/FU JSON field names.
- **Phase 8** — full notify→execute→fill→sell loop. **Phase 9** — polish + Plugin Hub.

## Environment facts a fresh agent needs

**Component B (Python):**
- venv: `companion/.venv/Scripts/python.exe` (Python 3.11.9; `requests`, `pytest` installed).
- Tests: `companion/.venv/Scripts/python.exe -m pytest companion/tests -q` (42 passing).
- `companion/config.json` is **gitignored** and has a real `user_agent` set; `flip_history.db`
  and `alerts.jsonl` are gitignored runtime artifacts.

**Component A (Java/RuneLite):**
- Build needs **JDK 11**, NOT the system default JDK 25. Path:
  `C:\Program Files\Eclipse Adoptium\jdk-11.0.31.11-hotspot`.
- Compile: `JAVA_HOME="C:\Program Files\Eclipse Adoptium\jdk-11.0.31.11-hotspot" sh plugin/gradlew -p plugin build`
  (Gradle 8.10 wrapper; RuneLite `latest.release` resolved as **1.12.29.1**).
- Dev client: from `plugin/`, with that `JAVA_HOME`, `.\gradlew.bat run`. Login is set up via
  the Jagex `--insecure-write-credentials` flow → `~/.runelite/credentials.properties` (auto-login).
- `/ge-state` serves on **`http://127.0.0.1:8766/ge-state`** (loopback). Verified live: `ge_open`,
  `offers`, `free_slot`, `client_bounds`, and `widgets` with `confirm_button` + `ge_slot_0..7`
  (visibility flips between setup/slot screens — correct).
- GE widget ids come from `net.runelite.api.gameval.InterfaceID.GeOffers` (`SETUP_CONFIRM`,
  `INDEX_0..7`, `COLLECTALL`, `BACK`, `SETUP`, `UNIVERSE`). Introspect the cached jar with
  `javap` if you need more — do not guess.

## Firm architecture rule (don't drift)

Scoring/ranking is the secret sauce → **stays server-side / in Component B**, never in the public
plugin (Plugin Hub requires open source). Plugin = thin client; API returns results only, never
thresholds. Local now, hosted at launch. See `docs/BACKLOG.md` #5.
