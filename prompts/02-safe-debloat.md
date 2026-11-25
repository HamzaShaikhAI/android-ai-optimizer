# Prompt 02: Verified Smart Debloating (UAD-NG Cross-Check)

Copy and paste this prompt after completing Prompt 01 (audit + backup):

```text
Run Stage 3 (Verified Smart Debloating) in Audit-First Mode.

Strict requirements:
1. Confirm `logs/packages_backup.txt` exists first; if missing, run `python scripts/backup_packages.py`.
2. Sync the Universal Android Debloater Next Generation database (`python scripts/sync_uad.py`) and cross-check my installed enabled packages against `cache/uad_lists.json` and `safety/hard_blocklist.json` (`python scripts/check_packages.py --tier Recommended`).
3. Present a Markdown approval table of ONLY `Recommended` candidates first (and list `Advanced` candidates in a separate section with feature-impact warnings):
   | Package Name | Vendor/List | UAD Tier | Purpose & Feature Impact | Risk Level | Exact Undo Command |
4. Never propose `Hard-Blocked`, `Unsafe`, or `Expert` packages.
5. Wait for my explicit yes/no selection before running `python scripts/debloat_packages.py --dry-run ...` and `--confirm ...`.
6. Log every removed package in `logs/removed_packages.txt` and `logs/rollback_log.json`.
```
