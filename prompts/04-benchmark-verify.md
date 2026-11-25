# Prompt 04: Before vs. After Benchmark & Verification Report

Copy and paste this prompt after running debloating or performance tuning:

```text
Run Stage 5 (Benchmark & Verification) using `python scripts/benchmark_device.py`.

1. Measure post-optimization RAM (`dumpsys meminfo`), active background service records (`dumpsys activity services`), and cold-start launch latency (`TotalTime` ms via `am start -W`) for my top daily apps.
2. Compare against `logs/benchmark_before.json` (if captured) and generate `logs/optimization_report.md`.
3. Remind me if a reboot is needed to activate Cached Apps Freezer (`use_freezer=true`), and summarize exact rollback commands if I want to revert any change.
```
