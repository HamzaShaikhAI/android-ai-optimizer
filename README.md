<div align="center">

# 📱 Android AI Optimizer (for Google Antigravity)

**A zero-dependency, safety-first MCP server and 5-stage ADB optimization pipeline that lets AI agents audit, debloat, and tune non-rooted Android devices with 1-click rollback.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-JSON--RPC%202.0-8A2BE2)](.agents/mcp_config.json)
[![Android SDK 28+](https://img.shields.io/badge/Android-SDK%2028%2B-3DDC84?logo=android&logoColor=white)](#supported-devices--oem-quirks)
[![Tests](https://img.shields.io/badge/Unit%20Tests-12%2F12%20Passing-brightgreen)](tests/test_safety_and_uad.py)
[![Security Policy](https://img.shields.io/badge/Security-Policy-orange)](SECURITY.md)
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Local-teal)](PRIVACY.md)

[Quickstart](#-quickstart-wired--wireless-adb) •
[Architecture](#-4-layer-safety-architecture) •
[Real-Device Benchmarks](#-verified-real-device-benchmark-oppo-a57) •
[Safety & Rollback](#-safety-guardrails--1-click-rollback) •
[FAQ](#-frequently-asked-questions)

</div>

---

> [!WARNING]
> **Use at your own risk.** Modifying system packages and Android framework settings via ADB can disrupt device features or cause bootloops if critical OEM services are removed improperly. This project enforces **Audit-First Mode**, pre-flight backups, **UAD-NG** cross-checking, offline bootloop blocklists, a `PreToolUse` safety hook, and **1-click rollback**, but you remain responsible for reviewing every proposed action before approving execution.

---

## ⚡ What Is Android AI Optimizer?

**Android AI Optimizer** is an open-source **Model Context Protocol (MCP)** toolkit for **Google Antigravity** (IDE, CLI, and App) and compatible MCP clients that automates non-root Android performance tuning via **ADB (Android Debug Bridge)**.

Unlike blind shell scripts or risky "booster" apps, this project enforces a strict **Audit → Snapshot → UAD-NG Cross-Check → Human Approval → Execute → Benchmark** workflow. Every mutating MCP tool defaults to `dry_run=true`, validates inputs inside a zero-dependency Python 3.10+ MCP server ([mcp_server/server.py](mcp_server/server.py)), and logs exact undo commands for 100% reversible changes.

### Key Capabilities

- **Zero-Dependency Scoped MCP Server:** Built on Python 3.10+ stdlib (newline-delimited JSON-RPC 2.0 over stdio) with 10 scoped tools and **zero raw shell access**.
- **Hallucination-Proof Debloating:** Cross-references installed packages against the live [Universal Android Debloater Next Generation (UAD-NG)](https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation) database (`uad_lists.json`), surfaces `neededBy` dependency warnings, and enforces a local [safety/hard_blocklist.json](safety/hard_blocklist.json).
- **SDK-Aware AOSP Tuning:** Automatically adapts commands across Android 9–15 (`pm art dexopt-packages -r bg-dexopt` on Android 14+ / SDK 34+, `cmd game set` on Android 13+ / SDK 33+, Phenotype-safe Cached Apps Freezer persistence on Android 11+, and exact `appops` state restoration).
- **Wired & Wireless ADB Ready:** Auto-discovers `adb` on `PATH` or standard Android SDK paths and works identically over USB or Android 11+ Wireless Debugging.

---

## 📊 Verified Real-Device Benchmark (Oppo A57)

Tested live on a consumer budget phone (**OPPO CPH2387 / Oppo A57**) running **Android 14 (SDK 34)**, **ColorOS V14.0.0**, **MediaTek Helio G35 (`mt6765`)**, and **~3.88 GB RAM** (`13.62 GB` free on `/data`).

### System Resource Impact

| Metric | Before | After | Net Delta |
| :--- | :---: | :---: | :---: |
| **Free RAM** | 1,118.3 MB | **1,643.9 MB** | **+525.7 MB (+47.0%)** |
| **Used RAM** | 3,892.2 MB | **3,766.0 MB** | **-126.2 MB** |
| **Active Service Records** | 166 | **148** | **-18 background services** |
| **Bloatware Removed (User 0)** | 0 | **36 / 37 removed** | 1 OS-protected package throttled via AppOps |
| **ART `speed-profile` Apps** | 40 | **50+** | Partial `bg-dexopt` + targeted `speed-profile` |

### App Cold-Start Latency (`am start -W`)

| Target App | Before (ms) | After (ms) | Delta |
| :--- | :---: | :---: | :---: |
| **YouTube** (`com.google.android.youtube`) | 3,475 ms | **3,082 ms** | **-393 ms faster** |
| **Instagram** (`com.instagram.android`) | 3,178 ms | **3,075 ms** | **-103 ms faster** |
| **WhatsApp** (`com.whatsapp`) | 3,325 ms | 3,928 ms\* | \*Measured immediately post-`dex2oat` & DNS change |

> **Real-World Findings:**
> - Eliminated `com.heytap.mcs` (which was firing **2,307 wakeups/alarms**) and the Facebook background updater suite (`7m30s` background CPU + `37s` wakelocks).
> - Throttled background sensor/RAM hogs (`com.meesho.supply`, shopping apps, and social media) via `appops` + `rare` standby buckets while keeping WhatsApp, ProtonVPN, Truecaller, and alarms unrestricted.
> - When ColorOS 14 blocked `com.nearme.instant.platform` with `DELETE_FAILED_INTERNAL_ERROR`, the pipeline automatically handled the failure and restricted it via Module A AppOps throttling instead.
> - Note: On the Helio G35 (`mt6765`), `pm art dexopt-packages -r bg-dexopt` hit its 600s timeout after compiling key apps (`speed-profile` rose from 40 to 50) and gracefully continued to targeted `speed-profile` compilation and `sm fstrim`.

---

## 🏗️ 4-Layer Safety Architecture

```text
+------------------------------------------------------------------------+
| LAYER 1: Orchestration & Guardrails (Google Antigravity)               |
| - Root AGENTS.md & .agents/rules/ (Audit-First, Human Approval Gate)   |
| - .agents/skills/ (android-audit, android-debloat, android-tune)       |
| - .agents/hooks.json (PreToolUse hook blocking bootloop & placebo cmds) |
+-----------------------------------+------------------------------------+
                                    | MCP Protocol (JSON-RPC 2.0 / stdio)
+-----------------------------------v------------------------------------+
| LAYER 2: Zero-Dependency Scoped MCP Server (mcp_server/server.py)      |
| - 10 scoped, input-validated tools (zero raw shell access)             |
| - Enforces hard_blocklist.json + snapshot gate + dry_run=true default  |
| - Optional companion: FlashZ/adb-mcp (.agents/mcp_config.adbmcp.example)|
+---------------+-----------------------------------+--------------------+
                | USB / Wireless ADB                | Local JSON
+---------------v--------------------+  +-----------v--------------------+
| LAYER 3: Target Android Device     |  | LAYER 4: Safety Knowledge      |
| - PackageManager (`pm`) & ART      |  | - Runtime-synced UAD-NG        |
| - ActivityManager (`am`) & AppOps  |  |   (`cache/uad_lists.json`)     |
| - Settings & Storage (`sm fstrim`) |  | - `safety/hard_blocklist.json` |
| - Kernel cgroup v2 Freezer         |  | - `logs/rollback_log.json`     |
+------------------------------------+  +--------------------------------+
```

---

## 🚀 Quickstart (Wired & Wireless ADB)

### Prerequisites

- **Python 3.10+** (zero `pip install` dependencies required)
- **Android SDK Platform-Tools (`adb`)** installed — see [docs/SETUP_ADB.md](docs/SETUP_ADB.md)
- **Google Antigravity** (or any MCP-compatible AI coding agent)

### 1. Clone the Repository

```bash
git clone https://github.com/HamzaShaikhAI/android-ai-optimizer.git
cd android-ai-optimizer
```

### 2. Connect Your Android Device

#### Option A: Wired USB (Recommended for First Run)
1. Enable **Developer options** on your phone (**Settings → About phone → tap Build number 7 times**).
2. Enable **USB debugging**.
   - **ColorOS / RealmeUI / OxygenOS:** Also toggle **Disable permission monitoring** ON in Developer options.
   - **MIUI / HyperOS:** Also enable **USB debugging (Security settings)**.
3. Plug in via USB, tap **Allow** on the RSA debugging prompt, and verify:
   ```bash
   adb devices -l
   ```

#### Option B: Wireless ADB (Android 11+ — No Cable Needed)
1. Connect your PC and phone to the same Wi-Fi network.
2. Enable **Wireless debugging** in **Developer options** → tap **Pair device with pairing code**.
3. Pair once and connect:
   ```bash
   adb pair <ip_address>:<pairing_port>
   adb connect <ip_address>:<connect_port>
   ```

### 3. Run the 5-Stage Pipeline in Google Antigravity

Open the repository folder in Google Antigravity. [.agents/mcp_config.json](.agents/mcp_config.json) automatically registers [mcp_server/server.py](mcp_server/server.py). Use the prompts in [`prompts/`](prompts/) or run the CLI tools directly:

1. **Stage 1 — Read-Only Audit:** `python scripts/audit_device.py` collects SDK level, OEM profile, RAM pressure, battery/alarm wakeups, `/data` free space, Cached Apps Freezer support, and ART dexopt state.
2. **Stage 2 — Pre-Flight Backup:** `python scripts/backup_packages.py` saves `logs/packages_backup.txt`, `logs/settings_backup.txt`, and initializes `logs/rollback_log.json`.
3. **Stage 3 — UAD-NG Check & Safe Debloat:** `python scripts/sync_uad.py` + `python scripts/check_packages.py` classify bloatware with `neededBy` dependency warnings; `python scripts/debloat_packages.py` executes approved User-0 removals.
4. **Stage 4 — SDK-Aware Tuning:** `python scripts/tune_performance.py` applies approved modules (AppOps + standby buckets, Cached Apps Freezer if kernel supports it, ART `bg-dexopt` + targeted `speed-profile`, `0.5x` animations, `disable_window_blurs`, Private DNS, and Android 12+ Game Mode).
5. **Stage 5 — Benchmark Report:** `python scripts/benchmark_device.py` generates a before/after `logs/optimization_report.md`.

---

## Supported Devices & OEM Quirks

| OEM / OS | Required Developer Option Tweak | Critical Keep / Notes |
| :--- | :--- | :--- |
| **Oppo / Realme / OnePlus** (ColorOS / RealmeUI / OxygenOS) | Toggle **Disable permission monitoring** ON | OS-protected `com.oplus.*` packages may return `DELETE_FAILED_INTERNAL_ERROR`; throttle via Module A AppOps instead |
| **Xiaomi / Redmi / Poco** (MIUI / HyperOS) | Enable **USB debugging (Security settings)** | **Never** remove `com.miui.securitycenter` or `com.xiaomi.finddevice` (hard-blocked to prevent bootloops) |
| **Samsung** (One UI) | Standard USB Debugging | Keep `com.samsung.android.knox.*` and `spay` if using Secure Folder or Samsung Pay |
| **Pixel / Motorola / Nothing** (AOSP) | Standard USB Debugging | Minimal bloat; focus on AppOps, Cached Apps Freezer, ART `speed-profile`, and Private DNS |

See [docs/OEM_NOTES.md](docs/OEM_NOTES.md), [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md), and [docs/MYTHS_AND_TRAPS.md](docs/MYTHS_AND_TRAPS.md) for full details.

---

## 🛡️ Safety Guardrails & 1-Click Rollback

Every change is logged locally in `logs/rollback_log.json` and `logs/removed_packages.txt` (excluded from Git via [.gitignore](.gitignore)).

Restore a single removed app:
```bash
python scripts/restore_package.py --package <package_name>
```

Revert everything (removed packages, settings, Private DNS, Game Mode, and exact prior AppOps states):
```bash
python scripts/restore_package.py --undo-all
```

**Built-in Guardrails:**
- Enforces [safety/hard_blocklist.json](safety/hard_blocklist.json) in scripts, the MCP server, and [.agents/hooks.json](.agents/hooks.json).
- Blocks destructive placebo commands (`cmd package compile -m everything -a`, `adb shell su`, non-`--user 0` uninstalls).
- Automatically skips banking, UPI, authenticator, alarm, messaging, VPN, and accessibility packages during AppOps throttling (`never_throttle_keywords`).
- Keeps `pm trim-caches 100G` opt-in (`--trim-caches`) so healthy devices don't needlessly drop warm app caches.

---

## ❓ Frequently Asked Questions

**Does this require root or unlocking the bootloader?**
No. All optimizations use standard, non-root Android Debug Bridge (ADB) commands. Your warranty, Play Integrity, and banking/UPI apps remain intact.

**Will this work on Samsung, Xiaomi, OnePlus, Oppo, and Pixel?**
Yes. The pipeline automatically detects the OEM and Android SDK version (`SDK 28+`) and applies OEM-specific rules documented in [docs/OEM_NOTES.md](docs/OEM_NOTES.md).

**Can the AI accidentally uninstall a critical system app and cause a bootloop?**
The MCP server and scripts enforce [safety/hard_blocklist.json](safety/hard_blocklist.json), block raw shell execution, require a pre-flight backup snapshot, cross-check UAD-NG dependency warnings (`neededBy`), and default all mutating tools to `dry_run=true` until you explicitly approve.

---

## Running Tests

```bash
python -m unittest discover -s tests -v
```

---

## 📄 License, Security & Privacy

- **License:** Released under the [MIT License](LICENSE). Package classifications are dynamically fetched at runtime from [UAD-NG](https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation) into gitignored `cache/`.
- **Security:** Read our [Security Policy](SECURITY.md) for responsible disclosure and MCP threat-model details.
- **Privacy:** Read our [Privacy Policy](PRIVACY.md) — 100% local execution, zero telemetry.
