# Contributing to Android AI Optimizer

Thank you for helping make non-root Android optimization safer and better verified across OEMs!

## Core Engineering Principles

1. **Zero External Runtime Dependencies:** Keep `scripts/` and `mcp_server/server.py` Python 3.10+ stdlib-only.
2. **Audit-First & 100% Reversible:** Any new tweak module must capture prior device state in `logs/rollback_log.json` before mutating the phone.
3. **No Raw Shell in MCP:** `mcp_server/server.py` must expose only scoped, input-validated tools with `dry_run=true` by default.
4. **No Placebo or Root-Only Tweaks:** Keep `cmd package compile -m everything -a` and unrooted `setprop` hacks blocked (see [docs/MYTHS_AND_TRAPS.md](docs/MYTHS_AND_TRAPS.md)).
5. **Never Commit Personal Device Data:** Always check `git status` to ensure `logs/`, `cache/`, and personal serial numbers are excluded.

## Local Development & Testing

```bash
python -m compileall -q scripts mcp_server .agents/scripts tests
python -m unittest discover -s tests -v
```

Tests mock ADB device calls and isolate `ANDROID_OPTIMIZER_LOGS_DIR` so they run safely offline or even while a real device is plugged in.

## How to Help Right Now

- Add entries to [safety/hard_blocklist.json](safety/hard_blocklist.json) for newer OEM skins (HyperOS 2, ColorOS 15, One UI 7).
- Share verified before/after Stage 5 benchmarks using the **Device Compatibility & Benchmark Report** issue form.
- Check open [`good first issue`](https://github.com/HamzaShaikhAI/android-ai-optimizer/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) items.
