# Prompt 01: Read-Only Device Diagnostic Audit & Pre-Flight Snapshot

Copy and paste this prompt into Google Antigravity (IDE, CLI, or App) after connecting your Android device via USB or Wireless ADB:

```text
Run Stage 1 (Read-Only Diagnostic Audit) and Stage 2 (Pre-Flight Safety Snapshot) on my connected Android device.

Rules for this turn:
1. Do NOT uninstall, disable, or change any package, AppOps permission, or system setting yet.
2. Verify a single authorized device is connected (`adb` MCP tools or `python scripts/audit_device.py`).
3. Collect and summarize:
   - Device manufacturer, model, Android version, SDK level, and board/platform.
   - OEM skin quirks and any required Developer Options toggles from `.agents/rules/oem-quirks.md`.
   - Top RAM and 24-hour process memory consumers (`dumpsys meminfo`, `dumpsys procstats --hours 24`).
   - Top battery wake-lock and alarm wakeup offenders (`dumpsys batterystats`, `dumpsys alarm`), clearly separating essential apps (messaging, alarms, banking/UPI) from safe optimization targets.
   - Cached Apps Freezer support (`/sys/fs/cgroup/cgroup.controllers` and `use_freezer`) and ART dexopt state.
4. Capture the pre-flight reversible snapshot with `python scripts/backup_packages.py` so `logs/packages_backup.txt`, `logs/settings_backup.txt`, and `logs/rollback_log.json` exist.
5. Optionally run a baseline benchmark (`python scripts/benchmark_device.py --phase before --packages <my top 3 daily apps>`).
```
