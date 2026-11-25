## Summary

<!-- Describe what this PR changes and why. -->

## Related Issue

Closes #

## Checklist

- [ ] Ran `python -m unittest discover -s tests -v` and all tests pass.
- [ ] Ran `python -m compileall -q scripts mcp_server .agents/scripts tests`.
- [ ] No unrestricted raw shell tools added to `mcp_server/server.py` (mutating tools keep `dry_run=True` default & `confirm=True` gate).
- [ ] No personal device logs (`logs/`, `cache/`, serial numbers) included (`git status` verified).
- [ ] Any new tuning tweaks record exact prior state in `logs/rollback_log.json` for 1-click undo.
