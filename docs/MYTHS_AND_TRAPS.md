# Myths & Traps: What We Deliberately Avoid

Many viral scripts, YouTube tutorials, and generic LLM outputs suggest "Android ADB optimization" commands that are placebo, waste gigabytes of storage, or hurt performance. This repository intentionally blocks or avoids the following traps:

---

## 1. `cmd package compile -m everything -a` (and `-m speed -a` on Low-Storage Phones)
**Why people suggest it:** "Compile every app to native machine code for maximum speed!"

**Why it backfires:**
- Full ahead-of-time (`everything`) compilation produces native ELF binaries roughly **10× larger** than DEX bytecode.
- On 64 GB / 128 GB phones, running `-m everything -a` across hundreds of apps can consume several gigabytes of storage, fill `/data`, and actually **slow down app cold starts** because the OS has to read much larger compiled OAT files off eMMC/UFS storage.

**What we do instead (`Module C`):**
- Run Android's built-in profile-guided background optimizer: `pm art dexopt-packages -r bg-dexopt` on Android 14+ (ART Service) or `cmd package bg-dexopt-job` on Android 13 and earlier.
- Optionally compile only your **top 3–5 daily apps** using real usage profiles: `cmd package compile -m speed-profile -f <package>`.
- Only run `pm trim-caches 100G` when `/data` free space is genuinely low (`--trim-caches`); blindly wiping all app caches slows down immediate re-launches while apps rebuild caches.
- Treat `sm fstrim` as best-effort: on many modern non-rooted builds, `sm fstrim` throws `SecurityException` (`shell` UID lacks `MOUNT_FORMAT_FILESYSTEMS`), and Android already schedules `fstrim` automatically during idle charging.

---

## 2. Unrooted `setprop` "Performance" Hacks
**Why people suggest it:** Viral lists full of `adb shell setprop debug.hwui.renderer ...`, fake CPU/GPU governor flags, or touch-sampling overrides.

**Why it fails:**
- On non-rooted production builds, SELinux blocks writing protected system properties (`ro.*`, `persist.*`, kernel tunables), so commands silently fail or return `Permission denied`.
- Even non-persistent `debug.*` properties reset completely on reboot and rarely beat OEM display/HWUI defaults.

**What we do instead:**
- Stick strictly to documented, persistent, non-root Android framework interfaces (`settings put`, `device_config`, `cmd appops`, `am set-standby-bucket`, `cmd package`, `sm fstrim`, `cmd game`).

---

## 3. Blindly Force-Stopping Apps in a Loop (`am force-stop`)
**Why it backfires:**
- Force-stopping apps that have registered system broadcasts, FCM push listeners, or WorkManager jobs often causes Android or companion services to immediately cold-restart them—burning **more** CPU and battery than leaving them cached.
- Note: We only use `am force-stop` in Stage 5 (`benchmark_device.py`) specifically to measure true **cold-start** launch latency (`TotalTime` ms).

**What we do instead (`Module A` & `Module B`):**
- Restrict background execution privileges cleanly via `cmd appops set <pkg> RUN_ANY_IN_BACKGROUND ignore` and `am set-standby-bucket <pkg> rare|restricted`.
- Use Android's **Cached Apps Freezer** (`use_freezer=true`) so cached apps stay ready in RAM while consuming **0% CPU** in a frozen kernel cgroup.

---

## 4. Guessing System Package Safety From Names Alone
**Why it backfires:**
- Package names like `com.miui.securitycenter`, `com.xiaomi.finddevice`, `com.android.se`, or `com.google.android.ext.services` look like optional extras or telemetry to an LLM, yet removing them causes instant bootloops or breaks OS permissions/Play Integrity.

**What we do instead (Stage 3):**
- Enforce `safety/hard_blocklist.json` + `.agents/scripts/pretool_guard.py`.
- Cross-check every candidate against the community-curated **UAD-NG (`uad_lists.json`)** database and require an explicit Markdown approval table before execution.
