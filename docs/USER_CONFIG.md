# User configuration (fill this in)

Copy your answers here so Claude Code and future-you do not re-decide them each session.
This file is safe to commit if you avoid secrets (use placeholders for webhooks/tokens).

## Plugins

- **Target plugins:** Copilot + Flipping Utilities + standalone
- **active_plugin default:** `standalone` (until adapters exist)

## Wiki API

- **user_agent:** `ge-flip-assistant - YOUR_EMAIL@example.com`  
  Required. The Wiki API blocks generic library user-agents.

## Execution

- **execution.mode:** `approve_then_execute` | `notify_only` | `auto_execute`
- **runelite_window_title:** `RuneScape` (exact taskbar title — verify on your machine)
- **execution.dry_run:** `true` until actuator is tested

## Thresholds (handoff §8.7)

| Setting | Value |
|---------|-------|
| min_profit_per_item | 50 |
| min_roi_pct | 1.5 |
| min_hourly_volume | 200 |
| min_buy_price | 100 |
| max_buy_price | 50000000 |
| scan_all | true |
| watchlist | [] |
| members_only | false |

## Discord (optional, Phase 3+)

- **webhook_url:** (empty — set in local `config.json` only)
- Use a **bot token** in a server you own if reading channels — never a user token.

## OpenClaw (optional, Phase 3+)

- **allowCommands:** `system.run`, `system.notify`
- **system.notify from script:** [CONFIRM] — default to `windows` / `discord` routes

## Blocked until you provide files (Phase 5)

### Flipping Copilot (`~/.runelite/flipping-copilot/`)

- [ ] One redacted `acc_{hash}_{slot}.json`
- [ ] One line from `{hash}_un_acked.jsonl`
- [ ] Blocked-items section from `{profile}.profile.json`
- [ ] Note whether `flips_{accountId}.json` exists

### Flipping Utilities (`~/.runelite/flipping/`)

- [ ] One redacted `trades[]` entry with `history` from `<username>.json`

Place redacted samples in `docs/samples/` when ready (gitignore if sensitive).
