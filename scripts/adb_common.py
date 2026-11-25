"""Shared ADB utilities, safety blocklist checks, and rollback logging helpers."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = Path(os.environ.get("ANDROID_OPTIMIZER_LOGS_DIR") or (REPO_ROOT / "logs"))
CACHE_DIR = Path(os.environ.get("ANDROID_OPTIMIZER_CACHE_DIR") or (REPO_ROOT / "cache"))
SAFETY_DIR = REPO_ROOT / "safety"

HARD_BLOCKLIST_PATH = SAFETY_DIR / "hard_blocklist.json"
UAD_CACHE_PATH = CACHE_DIR / "uad_lists.json"
PACKAGES_BACKUP_PATH = LOGS_DIR / "packages_backup.txt"
SETTINGS_BACKUP_PATH = LOGS_DIR / "settings_backup.txt"
REMOVED_PACKAGES_PATH = LOGS_DIR / "removed_packages.txt"
ROLLBACK_LOG_PATH = LOGS_DIR / "rollback_log.json"

PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$|^android$")


class AdbDeviceError(RuntimeError):
    """Raised when ADB is missing, unauthorized, disconnected, or ambiguous."""


class AdbCommandError(RuntimeError):
    """Raised when an ADB command exits with a non-zero status."""


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    """Create local runtime directories (logs/ and cache/) if absent."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def validate_package_name(package: str) -> str:
    """Validate an Android package identifier to prevent shell injection."""
    cleaned = package.strip()
    if not PACKAGE_NAME_RE.match(cleaned):
        raise ValueError(
            f"Invalid Android package name: {package!r}. "
            "Expected reverse-domain identifier like 'com.example.app'."
        )
    return cleaned


def find_adb() -> str:
    """Locate the `adb` binary via ADB_PATH, PATH, or standard Android SDK locations."""
    env_adb = os.environ.get("ADB_PATH")
    if env_adb and Path(env_adb).is_file():
        return env_adb

    adb_bin = shutil.which("adb")
    if adb_bin:
        return adb_bin

    exe = "adb.exe" if os.name == "nt" else "adb"
    candidates = [
        Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / exe,
        Path("C:/platform-tools") / exe,
        Path("C:/adb") / exe,
        Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / exe,
        Path.home() / "Android" / "Sdk" / "platform-tools" / exe,
        Path("/usr/local/bin") / exe,
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.insert(0, Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / exe)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise AdbDeviceError(
        "Android Debug Bridge (`adb`) was not found on PATH or standard SDK locations. "
        "Install Android SDK Platform Tools or set ADB_PATH (see docs/SETUP_ADB.md)."
    )


def parse_adb_devices(output: str) -> list[dict[str, str]]:
    """Parse `adb devices -l` output into structured device entries."""
    devices: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        details = " ".join(parts[2:])
        devices.append({"serial": serial, "state": state, "details": details})
    return devices


def resolve_serial(serial: str | None = None) -> str:
    """Resolve and verify a single authorized ADB device serial."""
    requested = serial or os.environ.get("ADB_SERIAL") or None
    adb_bin = find_adb()

    devices: list[dict[str, str]] = []
    for attempt in range(8):
        proc = subprocess.run(
            [adb_bin, "devices", "-l"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if proc.returncode != 0:
            raise AdbDeviceError(f"Failed to query `adb devices -l`: {proc.stderr.strip()}")
        devices = parse_adb_devices(proc.stdout)
        # Wait briefly if the USB RSA handshake is mid-flight ('authorizing')
        if any(d["state"] == "authorizing" for d in devices) and not any(d["state"] == "device" for d in devices):
            if attempt < 7:
                time.sleep(0.5)
                continue
        break

    if not devices:
        raise AdbDeviceError(
            "No Android devices detected. Enable USB Debugging, connect via USB/Wireless ADB, "
            "and verify with `adb devices` (see docs/SETUP_ADB.md)."
        )

    if requested:
        matches = [d for d in devices if d["serial"] == requested]
        if not matches:
            available = ", ".join(f"{d['serial']} ({d['state']})" for d in devices)
            raise AdbDeviceError(f"Requested device {requested!r} not found. Connected: {available}")
        device = matches[0]
        if device["state"] != "device":
            raise AdbDeviceError(
                f"Device {requested!r} is in state {device['state']!r}. "
                "Unlock the phone and accept the RSA USB Debugging prompt (see docs/TROUBLESHOOTING.md)."
            )
        return requested

    authorized = [d for d in devices if d["state"] == "device"]
    if not authorized:
        states = ", ".join(f"{d['serial']}: {d['state']}" for d in devices)
        raise AdbDeviceError(
            f"No authorized device ready ({states}). Unlock your phone and accept USB debugging authorization."
        )
    if len(authorized) > 1:
        serials = ", ".join(d["serial"] for d in authorized)
        raise AdbDeviceError(
            f"Multiple authorized devices connected ({serials}). Re-run with `--serial <SERIAL>` or set ADB_SERIAL."
        )
    return authorized[0]["serial"]


def run_adb(
    args: list[str],
    serial: str | None = None,
    check: bool = True,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Execute an `adb` command targeting the resolved device serial."""
    adb_bin = find_adb()
    target = resolve_serial(serial)
    cmd = [adb_bin, "-s", target, *args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip()
        raise AdbCommandError(f"Command `{' '.join(cmd)}` failed (exit {proc.returncode}): {stderr}")
    return proc


def run_adb_shell(
    shell_args: list[str],
    serial: str | None = None,
    check: bool = True,
    timeout: int = 60,
) -> str:
    """Execute `adb -s <serial> shell ...` safely with POSIX shell-quoting per argument."""
    quoted_args = [shlex.quote(str(arg)) for arg in shell_args]
    proc = run_adb(["shell", *quoted_args], serial=serial, check=check, timeout=timeout)
    return proc.stdout


def load_blocklist(path: Path | None = None) -> dict[str, Any]:
    """Load the offline hard-blocklist JSON."""
    target = path or HARD_BLOCKLIST_PATH
    if not target.exists():
        return {"exact_packages": {}, "protected_prefixes": [], "never_throttle_keywords": []}
    return json.loads(target.read_text(encoding="utf-8"))


def is_hard_blocked(package: str, blocklist: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    """Return `(True, reason)` if `package` is hard-blocked from removal."""
    pkg = package.strip()
    data = blocklist if blocklist is not None else load_blocklist()
    exact = data.get("exact_packages", {})
    if pkg in exact:
        info = exact[pkg]
        return True, f"[{info.get('category', 'Protected')}] {info.get('reason', 'Critical system package')}"
    for prefix in data.get("protected_prefixes", []):
        if pkg.startswith(prefix):
            return True, f"Matches protected system namespace `{prefix}`"
    return False, None


def is_never_throttle(package: str, blocklist: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    """Return `(True, keyword)` if package looks like an essential app (banking/alarms/messaging)."""
    lowered = package.lower()
    data = blocklist if blocklist is not None else load_blocklist()
    for kw in data.get("never_throttle_keywords", []):
        if kw.lower() in lowered:
            return True, kw
    return False, None


def load_rollback_log(path: Path | None = None) -> dict[str, Any]:
    """Load `logs/rollback_log.json` or return an empty initialized ledger."""
    target = path or ROLLBACK_LOG_PATH
    if not target.exists():
        return {"version": 1, "created_at": utc_now_iso(), "actions": []}
    data = json.loads(target.read_text(encoding="utf-8"))
    if "actions" not in data or not isinstance(data["actions"], list):
        data["actions"] = []
    return data


def save_rollback_log(data: dict[str, Any], path: Path | None = None) -> Path:
    """Atomically persist the rollback ledger JSON."""
    target = path or ROLLBACK_LOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(target)
    return target


def append_rollback_action(action: dict[str, Any], path: Path | None = None) -> Path:
    """Append a single reversible action record to `logs/rollback_log.json`."""
    ledger = load_rollback_log(path)
    entry = {"timestamp": utc_now_iso(), **action}
    ledger["actions"].append(entry)
    return save_rollback_log(ledger, path)


def detect_oem_profile(props: dict[str, str]) -> dict[str, Any]:
    """Infer OEM skin and developer option quirks from `getprop` values."""
    manufacturer = (props.get("manufacturer") or "").strip().lower()
    brand = (props.get("brand") or "").strip().lower()
    display = (props.get("display_id") or "").strip().lower()
    miui_ver = (props.get("miui_version") or "").strip()
    oplus_ver = (props.get("oplus_version") or "").strip()

    if miui_ver or any(x in manufacturer or x in brand for x in ("xiaomi", "redmi", "poco")):
        return {
            "family": "Xiaomi (MIUI / HyperOS)",
            "prerequisite": "Enable 'USB debugging (Security settings)' in Developer Options (requires SIM + Mi Account).",
            "critical_keep": ["com.miui.securitycenter", "com.xiaomi.finddevice", "com.miui.home"],
            "notes": "Removing com.miui.securitycenter or com.xiaomi.finddevice causes a hard bootloop.",
        }
    if oplus_ver or any(x in manufacturer or x in brand for x in ("oppo", "realme", "oneplus")):
        return {
            "family": "Oppo / Realme / OnePlus (ColorOS / RealmeUI / OxygenOS)",
            "prerequisite": "Toggle 'Disable permission monitoring' ON in Developer Options.",
            "critical_keep": ["com.oplus.battery", "com.coloros.phonemanager", "com.oppo.launcher"],
            "notes": "Some com.oplus.* packages return DELETE_FAILED_INTERNAL_ERROR; use AppOps throttling instead.",
        }
    if "samsung" in manufacturer or "samsung" in brand:
        return {
            "family": "Samsung (One UI)",
            "prerequisite": "Standard USB Debugging works.",
            "critical_keep": ["com.sec.android.app.launcher", "com.samsung.android.honeyboard", "com.samsung.android.knox.*"],
            "notes": "Preserve Knox/Wallet packages if Secure Folder, Work Profile, or Samsung Pay is used.",
        }
    if any(x in manufacturer or x in brand or x in display for x in ("google", "motorola", "nothing", "sony", "asus")):
        return {
            "family": "AOSP / Pixel / Motorola / Nothing",
            "prerequisite": "Standard USB Debugging works.",
            "critical_keep": ["com.google.android.gms", "com.android.vending", "com.google.android.webview"],
            "notes": "Minimal OEM bloat; focus primarily on AppOps, Cached Apps Freezer, ART compilation, and fstrim.",
        }
    return {
        "family": f"Generic Android ({props.get('manufacturer', 'Unknown')})",
        "prerequisite": "Standard USB Debugging works; check vendor security toggles if settings writes fail.",
        "critical_keep": ["com.android.systemui", "com.android.settings", "com.android.phone"],
        "notes": "Cross-check every system package with UAD-NG and safety/hard_blocklist.json before removal.",
    }
