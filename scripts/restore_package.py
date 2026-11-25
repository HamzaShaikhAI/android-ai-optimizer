"""1-click rollback & restore utility for removed packages and modified tweaks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import (  # noqa: E402
    REMOVED_PACKAGES_PATH,
    ROLLBACK_LOG_PATH,
    AdbDeviceError,
    append_rollback_action,
    load_rollback_log,
    run_adb_shell,
    validate_package_name,
)


def read_removed_packages(path: Path | None = None) -> list[str]:
    """Read unique package names recorded in `logs/removed_packages.txt`."""
    target = path or REMOVED_PACKAGES_PATH
    if not target.exists():
        return []
    seen: list[str] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        pkg = line.strip()
        if pkg and not pkg.startswith("#") and pkg not in seen:
            seen.append(pkg)
    return seen


def remove_from_removed_log(pkg: str, path: Path | None = None) -> None:
    """Remove a restored package from `logs/removed_packages.txt`."""
    target = path or REMOVED_PACKAGES_PATH
    if not target.exists():
        return
    remaining = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip() != pkg]
    content = "\n".join(remaining) + ("\n" if remaining else "")
    target.write_text(content, encoding="utf-8")


def restore_packages(
    packages: list[str],
    serial: str | None = None,
    dry_run: bool = False,
    rollback_path: Path | None = None,
) -> int:
    """Restore User-0 uninstalled packages via `cmd package install-existing`."""
    if not packages:
        print("No packages specified or found in logs/removed_packages.txt.")
        return 0

    exit_code = 0
    for raw_pkg in packages:
        pkg = validate_package_name(raw_pkg)
        if dry_run:
            print(f"[DRY-RUN] Would run: adb shell cmd package install-existing {pkg}")
            continue
        try:
            out = run_adb_shell(["cmd", "package", "install-existing", pkg], serial=serial, check=False).strip()
            if "not found" in out.lower() or "inaccessible" in out.lower():
                out = run_adb_shell(["pm", "install-existing", pkg], serial=serial, check=False).strip()
        except AdbDeviceError as exc:
            print(f"ERROR `{pkg}`: {exc}", file=sys.stderr)
            return 1

        if "installed for user" in out.lower() or "success" in out.lower() or not out.lower().startswith("error"):
            remove_from_removed_log(pkg)
            append_rollback_action(
                {
                    "type": "restore_package",
                    "package": pkg,
                    "command": f"adb shell cmd package install-existing {pkg}",
                    "output": out,
                },
                path=rollback_path,
            )
            print(f"RESTORED `{pkg}` ({out or 'ok'}).")
        else:
            exit_code = 1
            print(f"FAILED restoring `{pkg}`: {out}", file=sys.stderr)
    return exit_code


def undo_recorded_tweaks(
    serial: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    rollback_path: Path | None = None,
) -> int:
    """Replay `undo_args` from `logs/rollback_log.json` in reverse chronological order."""
    ledger = load_rollback_log(rollback_path)
    actions: list[dict[str, Any]] = [
        a for a in reversed(ledger.get("actions", []))
        if a.get("type") not in ("restore_package", "undo_tweak")
        and (a.get("undo_args") or a.get("type") == "uninstall_user0")
    ]
    if limit is not None:
        actions = actions[:limit]

    if not actions:
        print("No reversible actions found in logs/rollback_log.json.")
        return 0

    for action in actions:
        if action.get("type") == "uninstall_user0" and action.get("package"):
            restore_packages([action["package"]], serial=serial, dry_run=dry_run, rollback_path=rollback_path)
            continue

        undo_args = action.get("undo_args")
        if isinstance(undo_args, list) and undo_args:
            if dry_run:
                print(f"[DRY-RUN] Would run: adb shell {' '.join(undo_args)}")
                continue
            out = run_adb_shell([str(x) for x in undo_args], serial=serial, check=False).strip()
            append_rollback_action(
                {
                    "type": "undo_tweak",
                    "reverted_action": action.get("type"),
                    "command": f"adb shell {' '.join(str(x) for x in undo_args)}",
                    "output": out,
                },
                path=rollback_path,
            )
            print(f"REVERTED `{action.get('type')}` via `{' '.join(str(x) for x in undo_args)}` ({out or 'ok'}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="1-click restore for removed Android packages and system tweaks.")
    parser.add_argument("positional_package", nargs="?", help="Optional single package name to restore.")
    parser.add_argument("--package", action="append", default=[], help="Package ID to restore (repeatable).")
    parser.add_argument("--all", action="store_true", help="Restore all packages recorded in logs/removed_packages.txt.")
    parser.add_argument("--undo-all", action="store_true", help="Revert all recorded tweaks and packages in logs/rollback_log.json.")
    parser.add_argument("--undo-last", type=int, help="Revert the last N recorded actions from logs/rollback_log.json.")
    parser.add_argument("--serial", help="Target ADB device serial.")
    parser.add_argument("--dry-run", action="store_true", help="Preview restore commands without executing.")
    args = parser.parse_args()

    try:
        if args.undo_all or args.undo_last is not None:
            return undo_recorded_tweaks(serial=args.serial, dry_run=args.dry_run, limit=args.undo_last)

        targets = list(args.package)
        if args.positional_package:
            targets.append(args.positional_package)
        if args.all:
            targets.extend(read_removed_packages())

        if not targets:
            parser.error("Provide a package name, `--package <pkg>`, `--all`, `--undo-last N`, or `--undo-all`.")

        # Preserve order without duplicates
        unique_targets = list(dict.fromkeys(targets))
        return restore_packages(unique_targets, serial=args.serial, dry_run=args.dry_run)
    except (ValueError, AdbDeviceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
