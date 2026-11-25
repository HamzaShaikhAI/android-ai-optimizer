---
name: android-audit
description: >-
  Run Stage 1 (read-only telemetry & diagnostic audit) and Stage 2 (pre-flight
  reversible snapshot) on a connected Android device via ADB MCP or scripts.
  Use when starting an optimization session, inspecting RAM/battery/wake-lock
  hogs, or backing up packages and settings before making changes.
---

# Android Audit & Pre-Flight Snapshot Skill

Always start here before proposing or applying any debloat or tweak.

## Step 1: Verify Single Authorized Device
- If the `adb` MCP server (`FlashZ/adb-mcp`) is active, call its device listing / property tools first.
- Otherwise run:
  `python scripts/audit_device.py --summary`
- If no device or multiple devices are attached, stop and ask the user which `--serial` to target, or point them to [docs/SETUP_ADB.md](../../docs/SETUP_ADB.md).

## Step 2: Gather Read-Only Telemetry (Stage 1)
Run:
`python scripts/audit_device.py`

This collects into `logs/device_audit_<timestamp>.json` (gitignored):
- Manufacturer, model, brand, Android release, SDK level, board/platform (for OEM quirk selection).
- RAM & process pressure (`dumpsys meminfo`, `dumpsys procstats --hours 24`).
- Battery & wake-lock / alarm hogs (`dumpsys batterystats`, `dumpsys alarm`).
- Package inventory (`pm list packages -e`, `-s`, `-3`, `-d`).
- Cached Apps Freezer kernel & `device_config` status (`/sys/fs/cgroup/cgroup.controllers`, `use_freezer`).
- ART dexopt summary (`dumpsys package dexopt`) and current animation/Private DNS settings.

## Step 3: Capture Pre-Flight Snapshot (Stage 2)
Before ANY mutation, run:
`python scripts/backup_packages.py`

Verify that the following local files were created in `logs/`:
- `logs/packages_backup.txt`
- `logs/settings_backup.txt`
- `logs/rollback_log.json`

## Step 4: Present Findings
Summarize:
1. Device & OEM profile (plus any OEM Developer Options prerequisites from `.agents/rules/oem-quirks.md`).
2. Top RAM & 24h process memory consumers.
3. Top battery/alarm wakeup offenders (flagging messaging/banking/alarms as do-not-throttle).
4. Freezer & ART compilation readiness.
5. Next step: ask the user whether to proceed to Stage 3 (`android-debloat`) or Stage 4 (`android-tune`).
