---
trigger: always_on
description: Mandatory safety guardrails, audit-first workflow, human approval gates, and rollback guarantees for all Android ADB operations.
---

# Android Optimizer Safety Guardrails

Follow these rules strictly on every turn when interacting with an Android device.

## 1. Audit-First Mode (No Blind Mutations)
- On a new session or device, run **read-only diagnostics** (`scripts/audit_device.py` or read-only `adb` MCP tools like `dumpsys`, `get_setting`, `list_packages`) first.
- Never execute `pm uninstall`, `pm disable-user`, `cmd appops set`, `am set-standby-bucket`, `device_config put`, `settings put`, or `cmd game` until a pre-flight backup exists (`logs/packages_backup.txt`, `logs/settings_backup.txt`, `logs/rollback_log.json`).

## 2. Mandatory Snapshot Before Changes
- Always verify `logs/packages_backup.txt` and `logs/settings_backup.txt` exist for the target device before proposing or running any destructive or mutating change.
- If missing, run `python scripts/backup_packages.py` first.

## 3. UAD-NG Cross-Check & Hard Blocklist
- Never guess what a system package does from its package name alone.
- Always run `python scripts/sync_uad.py` and `python scripts/check_packages.py` to classify packages against both:
  1. `safety/hard_blocklist.json` (offline critical OS/OEM/banking blocklist)
  2. Universal Android Debloater Next Generation (`uad_lists.json`)
- Tier policy:
  - **Hard-Blocked**: Refuse removal (`com.android.systemui`, `com.android.phone`, `com.android.settings`, launchers, active keyboards/IMEs, telecom, WebView, Play Services/Store, OEM bootloop packages like `com.miui.securitycenter` and `com.xiaomi.finddevice`, banking/UPI/authenticator apps).
  - **Unsafe / Expert**: Do NOT recommend removal. Warn clearly if the user asks manually.
  - **Advanced**: Present only with explicit explanation of which OEM/optional feature breaks.
  - **Recommended**: Eligible for proposed debloat table after user confirmation.

## 4. Human Approval Gate
- Before executing any debloat (`pm uninstall -k --user 0`) or system tweak, present a Markdown table with:
  `| Package / Setting | Category / Tier | Purpose & Impact | Risk Level | Exact Undo Command |`
- Wait for explicit user confirmation (`yes` / selected items) before executing.
- Prefer the built-in zero-dependency scoped MCP server (`mcp_server/server.py`, which exposes zero raw shell tools); if `adbmcp` is enabled, keep `ADB_MCP_ALLOW_SHELL` at `"0"`.

## 5. Reversible Execution & Rollback Logging
- Only uninstall packages for User 0 (`pm uninstall -k --user 0 <package>`), never touch `/system`.
- Every removed package must be appended to `logs/removed_packages.txt` and recorded with its exact restore command (`adb shell cmd package install-existing <package>`) in `logs/rollback_log.json`.
- Every modified setting, AppOps rule, standby bucket, freezer flag, DNS setting, or game mode tweak must record its prior value in `logs/rollback_log.json`.

## 6. Prohibited Placebo & Harmful Tweaks
- **NEVER** run `cmd package compile -m everything -a` or `cmd package compile -m speed -a` (bloats storage ~10x and degrades I/O). Use `cmd package bg-dexopt-job` or targeted `cmd package compile -m speed-profile -f <pkg>`.
- **NEVER** run unverified root/SELinux `setprop` hacks (e.g., fake CPU/GPU/touch/hwui props) or `adb shell su`.
- **NEVER** throttle background execution (`RUN_ANY_IN_BACKGROUND ignore` or `restricted` standby bucket) on alarms/clocks, messaging/calls, accessibility services, VPNs, or UPI/banking/authenticator apps.
