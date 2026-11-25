"""Stage 2: Pre-flight reversible snapshot of packages and system settings."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import (  # noqa: E402
    LOGS_DIR,
    PACKAGES_BACKUP_PATH,
    REMOVED_PACKAGES_PATH,
    ROLLBACK_LOG_PATH,
    SETTINGS_BACKUP_PATH,
    AdbDeviceError,
    ensure_dirs,
    load_rollback_log,
    run_adb_shell,
    save_rollback_log,
    utc_now_iso,
)


def capture_snapshot(serial: str | None = None) -> dict[str, Path]:
    """Capture package inventories, settings dumps, and initialize rollback logs."""
    ensure_dirs()
    ts = utc_now_iso()

    all_pkgs = run_adb_shell(["pm", "list", "packages"], serial=serial)
    enabled_pkgs = run_adb_shell(["pm", "list", "packages", "-e"], serial=serial)
    disabled_pkgs = run_adb_shell(["pm", "list", "packages", "-d"], serial=serial)

    packages_content = "\n".join(
        [
            f"# Android AI Optimizer Package Snapshot ({ts})",
            "# === ALL PACKAGES ===",
            all_pkgs.strip(),
            "",
            "# === ENABLED PACKAGES ===",
            enabled_pkgs.strip(),
            "",
            "# === DISABLED PACKAGES ===",
            disabled_pkgs.strip(),
            "",
        ]
    )
    PACKAGES_BACKUP_PATH.write_text(packages_content, encoding="utf-8")

    global_settings = run_adb_shell(["settings", "list", "global"], serial=serial, check=False)
    system_settings = run_adb_shell(["settings", "list", "system"], serial=serial, check=False)
    secure_settings = run_adb_shell(["settings", "list", "secure"], serial=serial, check=False)

    settings_content = "\n".join(
        [
            f"# Android AI Optimizer Settings Snapshot ({ts})",
            "# === GLOBAL ===",
            global_settings.strip(),
            "",
            "# === SYSTEM ===",
            system_settings.strip(),
            "",
            "# === SECURE ===",
            secure_settings.strip(),
            "",
        ]
    )
    SETTINGS_BACKUP_PATH.write_text(settings_content, encoding="utf-8")

    if not REMOVED_PACKAGES_PATH.exists():
        REMOVED_PACKAGES_PATH.write_text("", encoding="utf-8")

    if not ROLLBACK_LOG_PATH.exists():
        save_rollback_log(load_rollback_log(ROLLBACK_LOG_PATH), ROLLBACK_LOG_PATH)

    return {
        "packages_backup": PACKAGES_BACKUP_PATH,
        "settings_backup": SETTINGS_BACKUP_PATH,
        "removed_packages": REMOVED_PACKAGES_PATH,
        "rollback_log": ROLLBACK_LOG_PATH,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 2: Export reversible package and settings snapshots.")
    parser.add_argument("--serial", help="Target ADB device serial (or set ADB_SERIAL).")
    args = parser.parse_args()

    try:
        paths = capture_snapshot(serial=args.serial)
    except AdbDeviceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Pre-flight safety snapshot complete:")
    for label, path in paths.items():
        print(f"- {label}: {path.relative_to(LOGS_DIR.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
