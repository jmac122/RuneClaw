# RuneClaw

OSRS Grand Exchange flipping assistant: suggest flips, score entry quality, notify, and
optionally place offers via an external click actuator.

**Spec:** [HANDOFF_ge_flip_assistant.md](HANDOFF_ge_flip_assistant.md)  
**Agent guide:** [CLAUDE.md](CLAUDE.md)  
**Your local settings:** [docs/USER_CONFIG.md](docs/USER_CONFIG.md)

## Components

| Path | Role |
|------|------|
| `companion/` | Python service — Wiki engine, scorer, notifications, actuator |
| `plugin/` | RuneLite plugin (Java) — in-client UI + `/ge-state` for clicks |

## Prerequisites

- **Python 3.11+**
- **Java 11 + Gradle** (only when building `plugin/`, Phase 6+)
- **RuneLite** client (Phase 4+ for actuator, Phase 6+ for plugin)

## Quick start

```bash
# From repo root (recommended)
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_config.py
# Edit companion/config.json — set user_agent (required by Wiki API)

python companion/ge_flip_watcher.py --once
```

Or work inside `companion/`:

```bash
cd companion
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Windows (PowerShell)** — copy config without `cp`:

```powershell
python scripts/setup_config.py
# or: Copy-Item companion\config.json.example companion\config.json
```

Run tests:

```bash
pip install pytest
pytest companion/tests -q
```

## Build phases

Implementation order is in **HANDOFF §7**. Phase prompts live in `prompts/`.

| Phase | What |
|-------|------|
| 1 | Wiki fetch, tax, filters, `--once` |
| 2 | SQLite + scorer |
| 3 | Notifications + execution orchestration |
| 4 | pyautogui actuator |
| 5 | Position readers (needs JSON samples) |
| 6–8 | RuneLite plugin + full loop |
| 9 | Polish |

## Ports (localhost only)

| Service | Default port |
|---------|----------------|
| Companion HTTP API | 8765 |
| Plugin `/ge-state` | 8766 |

## Config

- Committed template: `companion/config.json.example`
- Local config (gitignored): `companion/config.json`
- Never commit secrets, Discord webhooks, or tokens

## License

See [LICENSE](LICENSE).
