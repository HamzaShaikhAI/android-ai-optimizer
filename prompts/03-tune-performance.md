# Prompt 03: Modular Performance & Battery Tuning (Modules A–F)

Copy and paste this prompt to review and apply non-root Android optimizations:

```text
Inspect my Stage 1 audit results and propose a targeted Stage 4 optimization plan using only the verified non-root modules below:

- Module A (AppOps & Standby Buckets): Identify non-essential RAM/wakeup hogs (never messaging, alarms/clocks, VPNs, accessibility services, or banking/UPI apps) to throttle with `tune_performance.py --module appops`.
- Module B (Cached Apps Freezer): Check if my kernel supports cgroup v2 `freezer` (Android 11+); if yes, propose enabling both `cached_apps_freezer=enabled` and `use_freezer=true`.
- Module C (ART & Storage Maintenance): Propose version-aware ART compilation (`pm art dexopt-packages -r bg-dexopt` on Android 14+ or `cmd package bg-dexopt-job` on older Android), optional targeted `speed-profile` compilation for my top daily apps, and best-effort `sm fstrim` (plus `--trim-caches` only if `/data` free space is low). (Never use `compile -m everything -a` or `-m speed -a`.)
- Module D (UI Snappiness): Propose animation scales (`0.5` or `0.0`).
- Module E (System-Wide Private DNS): Ask which resolver I prefer (`dns.adguard-dns.com`, `one.one.one.one`, `dns.quad9.net`, or custom).
- Module F (Android 12+ Game Mode): Ask if I want performance mode / downscaling / FPS caps (`cmd game set` on Android 13+ or `cmd game mode`/`downscale` on Android 12) for any heavy games.

Show me a summary table with exact `--dry-run` commands and rollback steps, and wait for my confirmation before running `python scripts/tune_performance.py --confirm ...`.
```
