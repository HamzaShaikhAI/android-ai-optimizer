"""Stage 3: Cross-reference device packages against UAD-NG and safety/hard_blocklist.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import (  # noqa: E402
    UAD_CACHE_PATH,
    AdbDeviceError,
    is_hard_blocked,
    load_blocklist,
    run_adb_shell,
)
from audit_device import parse_packages_output  # noqa: E402
from sync_uad import normalize_uad_database  # noqa: E402

TIER_ORDER = ["Recommended", "Advanced", "Expert", "Unsafe", "Hard-Blocked", "Unknown"]

REMOVAL_ALIASES = {
    "safe": "Recommended",
    "recommended": "Recommended",
    "advanced": "Advanced",
    "expert": "Expert",
    "unsafe": "Unsafe",
}


def load_uad_database(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load normalized cached UAD-NG database if present."""
    target = path or UAD_CACHE_PATH
    if not target.exists():
        return {}
    raw = json.loads(target.read_text(encoding="utf-8"))
    return normalize_uad_database(raw)


def load_packages_from_backup(path: Path) -> list[str]:
    """Extract enabled (or all) package names from a `packages_backup.txt` file."""
    text = path.read_text(encoding="utf-8")
    enabled_marker = "# === ENABLED PACKAGES ==="
    disabled_marker = "# === DISABLED PACKAGES ==="
    if enabled_marker in text:
        after_enabled = text.split(enabled_marker, 1)[1]
        section = after_enabled.split(disabled_marker, 1)[0]
        return parse_packages_output(section)
    return parse_packages_output(text)


def classify_package(
    pkg: str,
    uad_db: dict[str, dict[str, Any]],
    blocklist: dict[str, Any],
) -> dict[str, Any]:
    """Classify a single Android package using offline hard-blocklist first, then UAD-NG."""
    blocked, block_reason = is_hard_blocked(pkg, blocklist)
    uad_entry = uad_db.get(pkg)

    if blocked:
        return {
            "package": pkg,
            "tier": "Hard-Blocked",
            "list": (uad_entry or {}).get("list", "System/OEM"),
            "description": block_reason or "Critical OS/OEM package",
            "risk": "CRITICAL (Blocked)",
            "eligible": False,
            "undo": "N/A (Refused)",
        }

    if uad_entry:
        raw_removal = str(uad_entry.get("removal") or "Unknown").strip().lower()
        tier = REMOVAL_ALIASES.get(raw_removal, "Unknown")
        risk_map = {
            "Recommended": "Low",
            "Advanced": "Medium (breaks optional OEM feature)",
            "Expert": "High (breaks system features)",
            "Unsafe": "Critical (bootloop risk)",
        }
        desc = " ".join(str(uad_entry.get("description") or "").split())
        needed_by = uad_entry.get("neededBy") or []
        warning = str(uad_entry.get("warning") or "").strip()
        extras: list[str] = []
        if warning:
            extras.append(f"Warning: {warning}")
        if needed_by:
            extras.append(f"Needed by: {', '.join(str(x) for x in needed_by[:4])}")
        if extras:
            desc = f"{desc} ({'; '.join(extras)})" if desc else "; ".join(extras)
        if len(desc) > 160:
            desc = desc[:157] + "..."
        return {
            "package": pkg,
            "tier": tier,
            "list": str(uad_entry.get("list") or "Misc"),
            "description": desc or "Listed in UAD-NG without description.",
            "risk": risk_map.get(tier, "Unknown"),
            "eligible": tier in ("Recommended", "Advanced"),
            "needed_by": needed_by,
            "undo": f"adb shell cmd package install-existing {pkg}",
        }

    return {
        "package": pkg,
        "tier": "Unknown",
        "list": "Unlisted",
        "description": "Not in UAD-NG database (likely user-installed or newer OEM service).",
        "risk": "Review manually",
        "eligible": False,
        "undo": f"adb shell cmd package install-existing {pkg}",
    }


def classify_packages(
    packages: list[str],
    uad_db: dict[str, dict[str, Any]],
    blocklist: dict[str, Any],
) -> list[dict[str, Any]]:
    """Classify and sort packages by safety tier and package name."""
    tier_rank = {name: idx for idx, name in enumerate(TIER_ORDER)}
    results = [classify_package(pkg, uad_db, blocklist) for pkg in sorted(set(packages))]
    results.sort(key=lambda item: (tier_rank.get(item["tier"], 99), item["package"]))
    return results


def render_markdown_table(rows: list[dict[str, Any]]) -> str:
    """Format package classifications into a human-approval Markdown table."""
    if not rows:
        return "No packages matched the requested tier filter.\n"
    lines = [
        "| Package Name | Vendor/List | UAD Tier | Purpose & Feature Impact | Risk Level | Exact Undo Command |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for row in rows:
        desc = row["description"].replace("|", "\\|")
        lines.append(
            f"| `{row['package']}` | {row['list']} | **{row['tier']}** | {desc} | {row['risk']} | `{row['undo']}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-reference Android packages against UAD-NG & hard blocklist.")
    parser.add_argument("--serial", help="Target ADB device serial (or set ADB_SERIAL).")
    parser.add_argument("--packages-file", type=Path, help="Read packages from a backup file instead of live ADB.")
    parser.add_argument("--uad-file", type=Path, default=UAD_CACHE_PATH, help="Path to cached uad_lists.json.")
    parser.add_argument(
        "--tier",
        nargs="+",
        default=["Recommended"],
        help="Tiers to display (e.g. Recommended Advanced, or 'all').",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    if args.packages_file:
        packages = load_packages_from_backup(args.packages_file)
    else:
        try:
            raw_pkgs = run_adb_shell(["pm", "list", "packages", "-e"], serial=args.serial)
        except AdbDeviceError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        packages = parse_packages_output(raw_pkgs)

    uad_db = load_uad_database(args.uad_file)
    if not uad_db:
        print(
            "WARNING: Cached UAD-NG database not found at cache/uad_lists.json. "
            "Run `python scripts/sync_uad.py` first for full classification.",
            file=sys.stderr,
        )

    blocklist = load_blocklist()
    classified = classify_packages(packages, uad_db, blocklist)

    if "all" not in [t.lower() for t in args.tier]:
        allowed_tiers = {t.lower() for t in args.tier}
        filtered = [row for row in classified if row["tier"].lower() in allowed_tiers]
    else:
        filtered = classified

    if args.format == "json":
        print(json.dumps({"total_scanned": len(classified), "matched": len(filtered), "packages": filtered}, indent=2))
    else:
        print(f"Scanned `{len(classified)}` enabled packages; matched `{len(filtered)}` for tier(s): {', '.join(args.tier)}.\n")
        print(render_markdown_table(filtered), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
