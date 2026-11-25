---
name: android-tune
description: >-
  Apply Stage 4 (Modules A-F: AppOps/standby buckets, Cached Apps Freezer, ART
  bg-dexopt/speed-profile & fstrim, animation scaling, Private DNS, and Android
  12+ Game Mode) and Stage 5 (before/after benchmarking & optimization_report.md).
  Use when tuning Android responsiveness, battery standby, or gaming FPS.
---

# Android Performance Tuning & Benchmarking Skill (Stages 4 & 5)

## Prerequisites
- Confirm `logs/packages_backup.txt` and `logs/settings_backup.txt` exist (run `python scripts/backup_packages.py` if missing).
- Check OEM Developer Options prerequisites in `.agents/rules/oem-quirks.md` (especially Oppo/ColorOS "Disable permission monitoring" and Xiaomi/MIUI "USB debugging (Security settings)").

## Available Modules (Stage 4)
Present relevant modules to the user and get approval before executing:
- **Module A (`appops`)**: Restrict background execution (`RUN_ANY_IN_BACKGROUND ignore`, `RUN_IN_BACKGROUND ignore`) and/or set standby buckets (`rare` / `restricted` on Android 11+) on non-essential heavy apps. Saves exact prior AppOps mode (`default`/`allow`) for accurate rollback. NEVER target alarms, messaging, dialers, accessibility, VPNs, or banking/UPI apps.
- **Module B (`freezer`)**: On Android 11+ (`SDK >= 30`), verify `freezer` in `/sys/fs/cgroup/cgroup.controllers`, then set BOTH `settings put global cached_apps_freezer enabled` and `device_config put activity_manager_native_boot use_freezer true` (prevents GMS Phenotype sync overrides; activates after reboot).
- **Module C (`art`)**: Runs `pm art dexopt-packages -r bg-dexopt` on Android 14+ (`SDK >= 34`) or `cmd package bg-dexopt-job` on Android 13 and older, optional targeted `cmd package compile -m speed-profile -f <pkg>`, opt-in `--trim-caches` only when storage is low, and best-effort `sm fstrim` (gracefully handles OEM shell UID restrictions). NEVER run `compile -m everything -a`.
- **Module D (`animations`)**: Set `window_animation_scale`, `transition_animation_scale`, and `animator_duration_scale` (default `0.5`).
- **Module E (`dns`)**: Configure `private_dns_mode=hostname` and `private_dns_specifier` (e.g., `dns.adguard-dns.com`, `one.one.one.one`, `dns.quad9.net`, or custom host) on Android 9+.
- **Module F (`game`)**: Android 12+ (`SDK >= 31`) Game Mode performance (`cmd game mode performance` / `cmd game set --downscale 0.8 --fps 60` on Android 13+, `cmd game downscale` on Android 12).

Always preview with `--dry-run` first, then run with `--confirm`:
`python scripts/tune_performance.py --module animations --scale 0.5 --dry-run`
`python scripts/tune_performance.py --module animations --scale 0.5 --confirm`

Every mutation automatically captures the prior value in `logs/rollback_log.json`.

## Stage 5: Verify & Benchmark
Run before and/or after tuning:
`python scripts/benchmark_device.py --packages <pkg1> <pkg2> <pkg3>`

This records `dumpsys meminfo`, active background services count, and cold-start `TotalTime` (ms) for target apps, generating `logs/optimization_report.md`.
