# Android AI Optimizer — Agent Operating Contract

This workspace turns Google Antigravity into an **audit-first, reversible Android optimizer** powered by a built-in, zero-dependency scoped MCP server (`mcp_server/server.py`, zero raw shell access) and deterministic cross-platform Python helper scripts (`scripts/`).

## Mandatory 5-Stage Pipeline

Never skip stages or execute mutating ADB commands on the first turn:

1. **Stage 1 — Read-Only Diagnostic Audit** (`python scripts/audit_device.py` or skill `android-audit`)
   - Identify device manufacturer, Android version, chipset/board, RAM/procstats pressure, battery/alarm wakeups, package inventory, Cached Apps Freezer status, and ART dexopt state.
2. **Stage 2 — Pre-Flight Reversible Snapshot** (`python scripts/backup_packages.py`)
   - Capture `logs/packages_backup.txt`, `logs/settings_backup.txt`, and initialize `logs/rollback_log.json` before changing anything.
3. **Stage 3 — Verified Smart Debloating** (`python scripts/sync_uad.py`, `python scripts/check_packages.py`, `python scripts/debloat_packages.py`)
   - Cross-reference packages against UAD-NG (`cache/uad_lists.json`) and `safety/hard_blocklist.json`.
   - Present a Markdown approval table (`Package Name`, `Tier`, `Purpose`, `Risk`, `Rollback`) and wait for explicit user approval before running `pm uninstall -k --user 0`.
4. **Stage 4 — Performance & Tweak Modules (A–F)** (`python scripts/tune_performance.py`)
   - Only apply modules the user selects (`appops`, `freezer`, `art`, `animations`, `dns`, `game`). Record pre-change state in `logs/rollback_log.json`.
5. **Stage 5 — Benchmark & Verification** (`python scripts/benchmark_device.py`)
   - Compare before/after RAM, background services, and cold-start launch latency (`TotalTime` ms) in `logs/optimization_report.md`.

## Hard Safety Rules

- **Never** uninstall or disable packages listed in `safety/hard_blocklist.json` or UAD-NG `Unsafe`/`Expert` tiers without an explicit user override warning.
- **Never** run `cmd package compile -m everything -a`, `cmd package compile -m speed -a` blindly, fake `setprop` tweaks, or root-requiring commands (`su`).
- **Never** enable `"ADB_MCP_ALLOW_SHELL": "1"` in `.agents/mcp_config.json` by default.
- **Never** commit `logs/`, `cache/`, device dumps, or personal serial numbers to Git.

## Repository Map

- `mcp_server/server.py` — Zero-dependency stdlib MCP stdio server exposing 10 scoped, audited tools (no raw shell).
- `.agents/mcp_config.json` — Workspace MCP server config (`android-optimizer` by default; optional `adbmcp` example alongside).
- `.agents/rules/` — Modular safety guardrails (`always_on`) and OEM quirks (`model_decision`).
- `.agents/skills/` — Step-by-step runbooks (`android-audit`, `android-debloat`, `android-tune`).
- `.agents/hooks.json` — `PreToolUse` command safety gate (`.agents/scripts/pretool_guard.py`).
- `safety/hard_blocklist.json` — Offline critical package blocklist and banking/UPI/auth heuristics.
- `scripts/` — Cross-platform Python 3.10+ stdlib tools (plus `.sh` wrappers).
- `prompts/` — Reusable stage prompts for Antigravity IDE, CLI, and App.
- `docs/` — Setup, OEM quirks, troubleshooting, and myths to avoid.
