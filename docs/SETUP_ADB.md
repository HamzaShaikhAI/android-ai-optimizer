# Setting Up ADB, Antigravity, and `FlashZ/adb-mcp`

This guide covers connecting your Android device to your computer (or running on-device with Termux + Shizuku) and wiring up Google Antigravity with `FlashZ/adb-mcp`.

---

## 1. Install Android SDK Platform Tools (`adb`)

### Windows
1. Download **Android SDK Platform Tools** from Google's official page:
   `https://developer.android.com/tools/releases/platform-tools`
2. Extract the ZIP (for example to `C:\platform-tools`).
3. Add `C:\platform-tools` to your Windows **PATH** environment variable, or install via Winget:
   ```powershell
   winget install Google.PlatformTools
   ```
4. Open a new terminal and verify:
   ```powershell
   adb version
   ```

### macOS
```bash
brew install android-platform-tools
adb version
```

### Linux (Debian / Ubuntu / Arch / Fedora)
```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y android-sdk-platform-tools

# Arch
sudo pacman -S android-tools

# Fedora
sudo dnf install -y android-tools
```

---

## 2. Enable USB Debugging (or Wireless Debugging) on Android

1. Open **Settings > About phone**.
2. Tap **Build number** 7 times (or **MIUI/HyperOS version** / **OS version** on some OEMs) until you see *"You are now a developer!"*.
3. Open **Settings > System > Developer options** (or **Additional settings > Developer options**).
4. Enable **USB debugging**.
5. Check OEM-specific extra toggles in [OEM_NOTES.md](./OEM_NOTES.md):
   - **Oppo / Realme / OnePlus**: Enable **Disable permission monitoring**.
   - **Xiaomi / Redmi / Poco**: Enable **USB debugging (Security settings)**.
6. Connect your phone via USB cable (use a data-capable cable, set USB mode to **File Transfer / MTP** if needed), unlock the screen, and tap **Allow** on the *"Allow USB debugging?"* RSA fingerprint prompt (check *"Always allow from this computer"*).
7. Verify connection:
   ```bash
   adb devices -l
   ```
   You should see your serial followed by `device` (not `unauthorized` or `offline`).

### Optional: Wireless Debugging (Android 11+)
1. Enable **Wireless debugging** in **Developer options** (phone and PC must be on the same Wi-Fi network).
2. Tap **Wireless debugging > Pair device with pairing code**.
3. On your PC:
   ```bash
   adb pair <IP>:<PAIR_PORT>
   adb connect <IP>:<CONNECT_PORT>
   ```

---

## 3. Configure Google Antigravity MCP Server

### Built-In Zero-Dependency Scoped MCP Server (Default)
This repository ships a self-contained Python stdlib MCP server at `mcp_server/server.py`, pre-configured in `.agents/mcp_config.json`. It requires **zero `pip install` packages**, exposes **no unrestricted raw shell tool**, enforces `safety/hard_blocklist.json`, and keeps mutating tools in `dry_run: true` mode by default.

### Optional: Adding `FlashZ/adb-mcp` (`adbmcp`) for UI / Screenshot / Input Tools
If you also want `FlashZ/adb-mcp`'s ~90 general device/UI tools alongside `android-optimizer`:
1. Install `adbmcp` (requires Python 3.10+):
   ```bash
   pip install adbmcp
   ```
2. Copy `.agents/mcp_config.adbmcp.example.json` over `.agents/mcp_config.json` (keeping `"ADB_MCP_ALLOW_SHELL": "0"`).

### Multiple Devices?
Set `ADB_SERIAL` in your shell or `.agents/mcp_config.json` locally (do not commit personal serials!), or pass `--serial <SERIAL>` to scripts/MCP tools.

### Inspecting MCP Status in Antigravity
- **Antigravity IDE**: `...` menu > **MCP Servers** > **Manage MCP Servers** > **View raw config**
- **Antigravity CLI (`agy`)**: Run `/mcp` inside the TUI

### Optional PreToolUse Safety Hook (`.agents/hooks.json`)
`.agents/hooks.json` invokes `python ./scripts/pretool_guard.py` before shell commands run.
- **macOS / Linux users**: If your system only provides `python3` (without a `python` alias), update `.agents/hooks.json` locally to `python3 ./scripts/pretool_guard.py`, or set `"enabled": false` if you prefer managing confirmations manually.

---

## 4. On-Device (No PC) with Termux + Shizuku (`rish`)

`scripts/adb_common.py` and `mcp_server/server.py` natively support running **directly on the Android device inside Termux** using Shizuku's `rish` bridge—no PC required!

1. Install **Shizuku** and start it via **Wireless debugging** (Android 11+).
2. Install **Termux** (from F-Droid or GitHub Releases, not the deprecated Play Store package) and install Python (`pkg install python`).
3. In the Shizuku app, tap **Use Shizuku in terminal apps → Export files**, and place `rish` + `rish_shizuku.dex` into `$PREFIX/bin/` (or set `RISH_PATH`).
4. **Android 14+ requirement:** Mark the DEX read-only so `app_process` permits loading it:
   ```bash
   chmod +x $PREFIX/bin/rish
   chmod 400 $PREFIX/bin/rish_shizuku.dex
   ```
5. Verify Shizuku authorization (`Allow all the time` for Termux):
   ```bash
   export RISH_APPLICATION_ID="com.termux"
   rish -c "id"   # should output uid=2000(shell)
   ```
6. Run any pipeline script directly in Termux! Bridge detection is automatic inside Termux (or force it explicitly with `export ADB_BRIDGE=rish`):
   ```bash
   python scripts/audit_device.py
   python scripts/backup_packages.py
   ```
   *(All calls isolate stdin with `DEVNULL` and default `RISH_APPLICATION_ID=com.termux` so MCP stdio and piped loops remain safe.)*
