# OEM-Specific Quirks & Protected Packages Matrix

Android manufacturers customize permissions, background managers, and system packages heavily. Review your device's OEM row before running debloating or AppOps tuning.

| OEM / OS | Required Developer Option Tweak | Critical "Do Not Remove" / Quirk |
| :--- | :--- | :--- |
| **Oppo / Realme / OnePlus** (ColorOS / RealmeUI / OxygenOS) | Must toggle **Disable permission monitoring** ON in Developer Options | Some `com.oplus.*` packages (e.g., `com.oplus.ota` or App Market) are OS-protected and return `DELETE_FAILED_INTERNAL_ERROR`; use AppOps throttling (`--module appops`) instead of forcing uninstall. Keep `com.oplus.battery`, `com.coloros.phonemanager`, and your launcher. |
| **Xiaomi / Redmi / Poco** (MIUI / HyperOS) | Must enable **USB debugging (Security settings)** in Developer Options (stock ROMs require SIM + Mi Account) | **NEVER** remove `com.miui.securitycenter` or `com.xiaomi.finddevice` — removing either triggers an immediate bootloop into Recovery. Keep `com.miui.home` unless a verified replacement launcher is active. |
| **Samsung** (One UI) | Standard USB Debugging works | Keep `com.samsung.android.knox.*`, `com.samsung.android.spay`, and `com.samsung.android.authfw` if you rely on Secure Folder, Work Profile, Samsung Pass, or Samsung Pay/Wallet. Keep `com.sec.android.app.launcher` and `com.samsung.android.honeyboard` (unless an alternate keyboard is active). |
| **Google Pixel / Motorola / Nothing** (AOSP-like) | Standard USB Debugging works | Minimal pre-installed bloatware. Focus primarily on **Module A** (`appops` / standby buckets for heavy user apps), **Module B** (Cached Apps Freezer), **Module C** (ART `bg-dexopt-job` / `speed-profile` / `fstrim`), and **Module D/E** (animations + Private DNS). |

---

## Detailed Notes by Vendor

### Xiaomi (MIUI / HyperOS)
- If `pm uninstall` or `settings put` returns `SecurityException: Permission denial`, verify **USB debugging (Security settings)** is enabled in **Settings > Additional settings > Developer options**.
- `safety/hard_blocklist.json` explicitly hard-blocks `com.miui.securitycenter`, `com.xiaomi.finddevice`, and `com.miui.home`.

### Oppo / Realme / OnePlus (ColorOS / RealmeUI / OxygenOS)
- Without **Disable permission monitoring**, `cmd appops set` and `settings put` calls fail with `SecurityException`.
- Protected vendor packages returning `DELETE_FAILED_INTERNAL_ERROR` cannot be removed via `--user 0` on newer ColorOS/OxygenOS builds. Throttle their background execution instead or leave them untouched.

### Samsung (One UI)
- Samsung's Device Care (`com.samsung.android.lool`) handles some background sleeping automatically; avoid stacking aggressive `restricted` buckets on apps you already put in One UI Deep Sleep unless needed.
- Removing `com.sec.android.app.launcher` breaks Android 12+ gesture navigation & Recents even if you use a third-party launcher.

### Banking, UPI, Authenticators, and Critical Utilities
Never apply `RUN_ANY_IN_BACKGROUND ignore` or `restricted` standby buckets to:
- UPI & banking apps (GPay, PhonePe, Paytm, bank apps)
- 2FA authenticators, password managers, SMS/OTP, Dialer/Telecom
- Messaging apps (WhatsApp, Signal, Telegram), Alarms/Clocks, VPNs, Accessibility services

`scripts/tune_performance.py` automatically skips packages matching `never_throttle_keywords` in `safety/hard_blocklist.json`.
