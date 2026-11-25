---
trigger: model_decision
description: OEM-specific Android developer options, protected packages, and bootloop pitfalls for ColorOS/OxygenOS/RealmeUI, MIUI/HyperOS, Samsung One UI, and AOSP/Pixel/Nothing.
---

# OEM-Specific Quirks & Protected Packages

Inspect `ro.product.manufacturer`, `ro.product.brand`, and OS properties from Stage 1 (`audit_device.py`) before recommending tweaks or package removals.

## Oppo / Realme / OnePlus (ColorOS / RealmeUI / OxygenOS)
- **Prerequisite**: User must enable **Disable permission monitoring** in Developer Options (`Settings -> System/Additional settings -> Developer options`) for `adb` permission/AppOps writes to succeed.
- **Protected packages**: Packages like `com.oplus.ota` or vendor App Market may return `DELETE_FAILED_INTERNAL_ERROR` even with `--user 0`. Do not retry destructively; fall back to non-destructive AppOps throttling or standby buckets if appropriate and approved.
- **Keep**: `com.oplus.battery`, core OPlus system frameworks, launcher (`com.android.launcher` / `com.oppo.launcher`), and camera services.

## Xiaomi / Redmi / Poco (MIUI / HyperOS)
- **Prerequisite**: User must enable **USB debugging (Security settings)** in Developer Options (requires SIM card + Mi Account sign-in on stock ROMs) to modify settings, AppOps, or `device_config`.
- **CRITICAL BOOTLOOP BLOCKLIST**: NEVER remove `com.miui.securitycenter` or `com.xiaomi.finddevice` (Find Device / Mi Cloud security). Removing either causes a hard bootloop into Recovery on MIUI/HyperOS.
- **Keep**: `com.miui.home` (unless replaced and verified), `com.miui.powerkeeper` (test cautiously; only restrict telemetry, not core system).

## Samsung (One UI)
- **Prerequisite**: Standard USB Debugging works. Note that Android 14+ restricts sideload/ADB changes on some protected enterprise/Knox flows.
- **Careful with Knox & Wallet**: Never remove `com.samsung.android.knox.*`, `com.samsung.android.spay`, or `com.samsung.android.authfw` if the user relies on Secure Folder, Samsung Pass, Work Profile, or Samsung Pay/Wallet.
- **Keep**: One UI Home (`com.sec.android.app.launcher`), Samsung Keyboard (`com.samsung.android.honeyboard`) unless an alternative IME is installed and active.

## Google Pixel / Motorola / Nothing (AOSP-like)
- **Prerequisite**: Standard USB Debugging works.
- **Strategy**: Minimal OEM bloatware. Focus optimization on **Module A** (AppOps/standby buckets for heavy third-party apps), **Module B** (Cached Apps Freezer), **Module C** (`bg-dexopt-job`, `speed-profile`, `sm fstrim`), and **Module D/E** (animation scales + Private DNS).
- **Keep**: `com.google.android.gms`, `com.android.vending`, `com.google.android.webview`, Pixel Launcher, and Carrier Services.
