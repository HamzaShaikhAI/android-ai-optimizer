"""Stage 3: Safe, reversible User-0 package removal with blocklist & UAD-NG enforcement."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import (  # noqa: E402
    PACKAGES_BACKUP_PATH,
    REMOVED_PACKAGES_PATH,
    AdbCommandError,
    AdbDeviceError,
    append_rollback_action,
    ensure_dirs,
    is_hard_blocked,
    load_blocklist,
    run_adb_shell,
    validate_package_name,
)
from check_packages import classify_package, load_uad_database  # noqa: E402


def record_removed_package(pkg: str, removed_path: Path | None = None) -> None:
    """Append `pkg` to `logs/removed_packages.txt` if not already present."""
    target = removed_path or REMOVED_PACKAGES_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if target.exists():
        existing = {line.strip() for line in target.read_text(encoding="utf-8").splitlines() if line.strip()}
    if pkg not in existing:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(f"{pkg}\n")


def validate_removal_candidates(
    packages: list[str],
    allow_advanced: bool = False,
    allow_unknown: bool = False,
    uad_path: Path | None = None,
) -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    """Validate packages against syntax, hard_blocklist.json, and UAD-NG safety tiers."""
    blocklist = load_blocklist()
    uad_db = load_uad_database(uad_path)
    approved: list[dict[str, str]] = []
    rejected: list[tuple[str, str]] = []

    for raw_pkg in packages:
        try:
            pkg = validate_package_name(raw_pkg)
        except ValueError as exc:
            rejected.append((raw_pkg, str(exc)))
            continue

        blocked, block_reason = is_hard_blocked(pkg, blocklist)
        if blocked:
            rejected.append((pkg, f"HARD-BLOCKED: {block_reason}"))
            continue

        info = classify_package(pkg, uad_db, blocklist)
        tier = info["tier"]
        if tier in ("Unsafe", "Expert"):
            rejected.append((pkg, f"UAD-NG tier `{tier}` is blocked by safety policy ({info['risk']})."))
            continue
        if tier == "Advanced" and not allow_advanced:
            rejected.append((pkg, "UAD-NG tier `Advanced` requires `--allow-advanced` after reviewing feature impact."))
            continue
        if tier == "Unknown" and not allow_unknown:
            rejected.append((pkg, "Package is not in UAD-NG database; pass `--allow-unknown` only if you verified it."))
            continue

        approved.append({"package": pkg, "tier": tier, "description": info["description"]})

    return approved, rejected


def execute_debloat(
    packages: list[str],
    serial: str | None = None,
    dry_run: bool = False,
    confirm: bool = False,
    allow_advanced: bool = False,
    allow_unknown: bool = False,
    clear_data: bool = False,
    skip_backup_check: bool = False,
) -> int:
    """Validate and uninstall approved packages for User 0 with full rollback logging."""
    if not dry_run:
        ensure_dirs()
        if not skip_backup_check and not PACKAGES_BACKUP_PATH.exists():
            print(
                "ERROR: Pre-flight snapshot `logs/packages_backup.txt` not found. "
                "Run `python scripts/backup_packages.py` first (or pass `--skip-backup-check`).",
                file=sys.stderr,
            )
            return 1
    elif not skip_backup_check and not PACKAGES_BACKUP_PATH.exists():
        print(
            "NOTE: Pre-flight snapshot `logs/packages_backup.txt` not found yet; "
            "run `python scripts/backup_packages.py` before applying changes.",
            file=sys.stderr,
        )

    approved, rejected = validate_removal_candidates(
        packages,
        allow_advanced=allow_advanced,
        allow_unknown=allow_unknown,
    )

    for pkg, reason in rejected:
        print(f"BLOCKED `{pkg}`: {reason}", file=sys.stderr)

    if not approved:
        print("No eligible packages left to process.", file=sys.stderr)
        return 1 if rejected else 0

    uninstall_flags = ["--user", "0"] if clear_data else ["-k", "--user", "0"]
    print("Proposed User-0 removals:")
    for item in approved:
        print(f"  - {item['package']} [{item['tier']}] -> undo: adb shell cmd package install-existing {item['package']}")

    if dry_run:
        print("\n[DRY-RUN] No packages were modified on the device.")
        return 0

    if not confirm:
        answer = input("\nType 'yes' to execute `pm uninstall` for the packages above: ").strip().lower()
        if answer != "yes":
            print("Aborted by user. No changes made.")
            return 1

    exit_code = 0
    for item in approved:
        pkg = item["package"]
        try:
            out = run_adb_shell(["pm", "uninstall", *uninstall_flags, pkg], serial=serial, check=False).strip()
        except AdbDeviceError as exc:
            print(f"ERROR `{pkg}`: {exc}", file=sys.stderr)
            return 1

        if "Success" in out:
            record_removed_package(pkg)
            append_rollback_action(
                {
                    "type": "uninstall_user0",
                    "package": pkg,
                    "tier": item["tier"],
                    "command": f"adb shell pm uninstall {' '.join(uninstall_flags)} {pkg}",
                    "undo_command": f"adb shell cmd package install-existing {pkg}",
                }
            )
            print(f"REMOVED `{pkg}` ({out}).")
        else:
            exit_code = 1
            hint = ""
            if "DELETE_FAILED_INTERNAL_ERROR" in out:
                hint = " (OEM-protected package; consider AppOps throttling via `tune_performance.py --module appops` instead)"
            print(f"FAILED `{pkg}`: {out or 'unknown error'}{hint}", file=sys.stderr)

    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3: Safely uninstall approved bloatware for User 0.")
    parser.add_argument("packages", nargs="*", help="Android package IDs to uninstall.")
    parser.add_argument("--file", type=Path, help="Optional newline-separated file of package IDs.")
    parser.add_argument("--serial", help="Target ADB device serial.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview commands without executing.")
    parser.add_argument("--confirm", action="store_true", help="Skip interactive prompt (use only after user approval).")
    parser.add_argument("--allow-advanced", action="store_true", help="Allow UAD-NG `Advanced` tier packages.")
    parser.add_argument("--allow-unknown", action="store_true", help="Allow packages unlisted in UAD-NG (still enforces hard blocklist).")
    parser.add_argument("--clear-data", action="store_true", help="Omit `-k` to also wipe app data/cache on removal.")
    parser.add_argument("--skip-backup-check", action="store_true", help="Skip requiring logs/packages_backup.txt.")
    args = parser.parse_args()

    targets = list(args.packages)
    if args.file:
        targets.extend(
            line.strip()
            for line in args.file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not targets:
        parser.error("Provide one or more package IDs or `--file <path>`.")

    try:
        return execute_debloat(
            targets,
            serial=args.serial,
            dry_run=args.dry_run,
            confirm=args.confirm,
            allow_advanced=args.allow_advanced,
            allow_unknown=args.allow_unknown,
            clear_data=args.clear_data,
            skip_backup_check=args.skip_backup_check,
        )
    except AdbCommandError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
