---
name: android-debloat
description: >-
  Run Stage 3 (verified smart debloating) by syncing UAD-NG uad_lists.json,
  cross-checking installed packages against UAD-NG and safety/hard_blocklist.json,
  obtaining explicit user confirmation via an approval table, executing User 0
  removals, and logging 1-click rollback records. Use when the user asks to
  identify or remove Android bloatware safely.
---

# Verified Smart Debloating Skill (Stage 3)

Never guess package safety from package names. Follow every gate below.

## Step 1: Confirm Pre-Flight Backup Exists
Check that `logs/packages_backup.txt` exists. If missing, run:
`python scripts/backup_packages.py`

## Step 2: Sync UAD-NG Database & Classify Installed Packages
1. Fetch/refresh the UAD-NG package database locally (`cache/uad_lists.json`, gitignored):
   `python scripts/sync_uad.py`
2. Cross-reference installed enabled packages against UAD-NG and `safety/hard_blocklist.json`:
   `python scripts/check_packages.py --tier Recommended`
   (Or `--tier Recommended Advanced` if the user explicitly wants optional OEM feature removals inspected too.)

## Step 3: Present Mandatory Approval Table
Output a clear Markdown table for the user containing ONLY eligible candidates (`Recommended` by default; `Advanced` separately marked):

`| Package Name | Vendor/List | UAD Tier | Purpose & Feature Impact | Risk Level | Undo Command |`

Never include `Hard-Blocked`, `Unsafe`, or `Expert` packages as recommended removals. Call out any `Unknown` third-party apps separately if relevant.
Wait for explicit user confirmation naming which packages (or "all Recommended") to remove.

## Step 4: Dry-Run & Execute Approved Removals
1. Preview first:
   `python scripts/debloat_packages.py --dry-run <pkg1> <pkg2> ...`
2. Execute ONLY after user approval:
   `python scripts/debloat_packages.py --confirm <pkg1> <pkg2> ...`

The script automatically:
- Refuses any package in `safety/hard_blocklist.json`.
- Runs `adb shell pm uninstall -k --user 0 <pkg>`.
- Appends `<pkg>` to `logs/removed_packages.txt`.
- Appends the exact undo record (`adb shell cmd package install-existing <pkg>`) to `logs/rollback_log.json`.

## Step 5: Rollback Verification
Inform the user they can restore any package in one command:
`python scripts/restore_package.py --package <pkg>` (or `--all`).
