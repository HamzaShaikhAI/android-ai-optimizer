# Prompt 05: 1-Click Rollback & Restore

Copy and paste this prompt anytime you want to restore removed packages or revert tuning tweaks:

```text
Help me inspect `logs/removed_packages.txt` and `logs/rollback_log.json` and safely roll back changes.

1. List all removed packages and recorded system/AppOps/DNS/freezer tweaks from `logs/rollback_log.json`.
2. Preview the restore commands with `--dry-run` first (`python scripts/restore_package.py --dry-run ...`).
3. Wait for my confirmation on whether to restore a specific package (`--package <pkg>`), all removed packages (`--all`), or revert all recorded tweaks (`--undo-all`).
```
