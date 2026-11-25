"""Stage 1: Read-only Android telemetry & diagnostic audit."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import (  # noqa: E402
    LOGS_DIR,
    AdbDeviceError,
    detect_oem_profile,
    ensure_dirs,
    run_adb_shell,
    utc_now_iso,
)


def parse_packages_output(raw: str) -> list[str]:
    """Parse `pm list packages` output into sorted package names."""
    packages: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkg = line[len("package:") :].strip()
            if pkg:
                packages.append(pkg)
    return sorted(set(packages))


def parse_meminfo_summary(raw: str, top_n: int = 12) -> dict[str, Any]:
    """Extract total/free RAM figures and top PSS process lines from `dumpsys meminfo`."""
    total_ram = None
    free_ram = None
    used_ram = None
    top_processes: list[str] = []
    in_process_block = False

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("Total RAM:"):
            total_ram = stripped
        elif stripped.startswith("Free RAM:"):
            free_ram = stripped
        elif stripped.startswith("Used RAM:"):
            used_ram = stripped
        elif stripped.startswith("Total PSS by process:"):
            in_process_block = True
            continue
        elif in_process_block:
            if not stripped or stripped.startswith("Total PSS by OOM"):
                in_process_block = False
                continue
            if len(top_processes) < top_n:
                top_processes.append(stripped)

    return {
        "total_ram": total_ram,
        "free_ram": free_ram,
        "used_ram": used_ram,
        "top_pss_processes": top_processes,
    }


def parse_df_data(raw: str) -> dict[str, Any]:
    """Parse `df -k /data` output into human-readable storage stats."""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 2:
        return {"available_gb": None, "use_percent": None, "raw": raw.strip()}
    parts = lines[-1].split()
    # Expected POSIX/toybox df -k columns: Filesystem 1K-blocks Used Available Use% Mounted
    if len(parts) >= 5 and parts[3].isdigit():
        avail_kb = int(parts[3])
        use_pct = parts[4]
        return {
            "available_gb": round(avail_kb / (1024 * 1024), 2),
            "use_percent": use_pct,
            "raw": lines[-1],
        }
    return {"available_gb": None, "use_percent": None, "raw": lines[-1]}


def extract_lines_matching(raw: str, keywords: tuple[str, ...], limit: int = 25) -> list[str]:
    """Return up to `limit` trimmed lines containing any keyword (case-insensitive)."""
    matches: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(k in low for k in keywords):
            matches.append(stripped)
            if len(matches) >= limit:
                break
    return matches


def count_dexopt_filters(raw: str) -> dict[str, int]:
    """Summarize compiler filter distribution (`speed-profile`, `verify`, `quicken`, etc.)."""
    counts: dict[str, int] = {}
    pattern = re.compile(r"\[status=([a-zA-Z0-9_-]+)\]")
    for match in pattern.finditer(raw):
        status = match.group(1)
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def collect_audit(serial: str | None = None) -> dict[str, Any]:
    """Collect read-only telemetry across device props, RAM, storage, battery, packages, freezer, and ART."""
    def getprop(name: str) -> str:
        return run_adb_shell(["getprop", name], serial=serial, check=False).strip()

    props = {
        "manufacturer": getprop("ro.product.manufacturer"),
        "brand": getprop("ro.product.brand"),
        "model": getprop("ro.product.model"),
        "android_release": getprop("ro.build.version.release"),
        "sdk": getprop("ro.build.version.sdk"),
        "platform": getprop("ro.board.platform"),
        "display_id": getprop("ro.build.display.id"),
        "miui_version": getprop("ro.miui.ui.version.name"),
        "oplus_version": getprop("ro.build.version.oplusrom"),
        "bg_dexopt_filter": getprop("pm.dexopt.bg-dexopt"),
    }
    oem = detect_oem_profile(props)

    meminfo_raw = run_adb_shell(["dumpsys", "meminfo"], serial=serial, check=False, timeout=90)
    procstats_raw = run_adb_shell(["dumpsys", "procstats", "--hours", "24"], serial=serial, check=False, timeout=90)
    batterystats_raw = run_adb_shell(["dumpsys", "batterystats"], serial=serial, check=False, timeout=90)
    alarm_raw = run_adb_shell(["dumpsys", "alarm"], serial=serial, check=False, timeout=90)
    df_raw = run_adb_shell(["df", "-k", "/data"], serial=serial, check=False)

    enabled_pkgs = parse_packages_output(run_adb_shell(["pm", "list", "packages", "-e"], serial=serial))
    system_pkgs = parse_packages_output(run_adb_shell(["pm", "list", "packages", "-s"], serial=serial))
    third_party_pkgs = parse_packages_output(run_adb_shell(["pm", "list", "packages", "-3"], serial=serial))
    disabled_pkgs = parse_packages_output(run_adb_shell(["pm", "list", "packages", "-d"], serial=serial))

    cgroup_controllers = run_adb_shell(["cat", "/sys/fs/cgroup/cgroup.controllers"], serial=serial, check=False).strip()
    freezer_flag = run_adb_shell(
        ["device_config", "get", "activity_manager_native_boot", "use_freezer"],
        serial=serial,
        check=False,
    ).strip()
    freezer_setting = run_adb_shell(
        ["settings", "get", "global", "cached_apps_freezer"],
        serial=serial,
        check=False,
    ).strip()
    dexopt_raw = run_adb_shell(["dumpsys", "package", "dexopt"], serial=serial, check=False, timeout=90)

    def get_global_setting(key: str) -> str:
        return run_adb_shell(["settings", "get", "global", key], serial=serial, check=False).strip()

    settings_snapshot = {
        "window_animation_scale": get_global_setting("window_animation_scale"),
        "transition_animation_scale": get_global_setting("transition_animation_scale"),
        "animator_duration_scale": get_global_setting("animator_duration_scale"),
        "private_dns_mode": get_global_setting("private_dns_mode"),
        "private_dns_specifier": get_global_setting("private_dns_specifier"),
        "cached_apps_freezer": freezer_setting,
    }

    return {
        "audited_at": utc_now_iso(),
        "device_props": props,
        "oem_profile": oem,
        "storage_data": parse_df_data(df_raw),
        "memory": parse_meminfo_summary(meminfo_raw),
        "procstats_24h_highlights": extract_lines_matching(
            procstats_raw, ("proc ", "summary:", "total time"), limit=30
        ),
        "battery_wakeup_highlights": extract_lines_matching(
            batterystats_raw, ("wake lock", "top app", "estimated power use", "uid u0a"), limit=30
        ),
        "alarm_wakeup_highlights": extract_lines_matching(
            alarm_raw, ("wakeups", "alarm stats", "u0a"), limit=25
        ),
        "packages": {
            "enabled_count": len(enabled_pkgs),
            "system_count": len(system_pkgs),
            "third_party_count": len(third_party_pkgs),
            "disabled_count": len(disabled_pkgs),
            "enabled": enabled_pkgs,
            "system": system_pkgs,
            "third_party": third_party_pkgs,
            "disabled": disabled_pkgs,
        },
        "freezer": {
            "cgroup_controllers": cgroup_controllers,
            "kernel_supports_freezer": "freezer" in cgroup_controllers.split(),
            "use_freezer_flag": freezer_flag,
            "cached_apps_freezer_setting": freezer_setting,
        },
        "art_dexopt_summary": count_dexopt_filters(dexopt_raw),
        "current_settings": settings_snapshot,
    }


def format_summary_markdown(audit: dict[str, Any]) -> str:
    """Format a human-readable Markdown diagnostic summary."""
    props = audit["device_props"]
    oem = audit["oem_profile"]
    storage = audit.get("storage_data", {})
    mem = audit["memory"]
    pkgs = audit["packages"]
    freezer = audit["freezer"]
    settings = audit["current_settings"]

    lines = [
        "# Stage 1: Android Device Diagnostic Audit",
        "",
        f"- **Audited at**: `{audit['audited_at']}`",
        f"- **Device**: `{props.get('manufacturer')} {props.get('model')}` (Android `{props.get('android_release')}`, SDK `{props.get('sdk')}`, Platform `{props.get('platform')}`)",
        f"- **OEM Profile**: `{oem['family']}`",
        f"- **OEM Prerequisite**: {oem['prerequisite']}",
        f"- **`/data` Storage**: `{storage.get('available_gb')} GB` free (`{storage.get('use_percent')}` used)",
        "",
        "## Package Inventory",
        f"- Enabled: `{pkgs['enabled_count']}` | System: `{pkgs['system_count']}` | Third-Party: `{pkgs['third_party_count']}` | Disabled: `{pkgs['disabled_count']}`",
        "",
        "## Memory Pressure (`dumpsys meminfo`)",
        f"- {mem.get('total_ram') or 'Total RAM: N/A'}",
        f"- {mem.get('used_ram') or 'Used RAM: N/A'}",
        f"- {mem.get('free_ram') or 'Free RAM: N/A'}",
        "",
        "Top PSS Processes:",
    ]
    for proc in mem.get("top_pss_processes", [])[:10]:
        lines.append(f"- `{proc}`")

    lines.extend(
        [
            "",
            "## Cached Apps Freezer & ART Status",
            f"- Kernel freezer support (`/sys/fs/cgroup/cgroup.controllers`): `{freezer['kernel_supports_freezer']}` (`{freezer['cgroup_controllers'] or 'unavailable'}`)",
            f"- `use_freezer` flag: `{freezer['use_freezer_flag'] or 'unset'}` | `cached_apps_freezer` setting: `{freezer.get('cached_apps_freezer_setting') or 'unset'}`",
            f"- ART bg-dexopt target filter: `{props.get('bg_dexopt_filter') or 'default'}` | dexopt summary: `{json.dumps(audit['art_dexopt_summary'])}`",
            "",
            "## Current Global Settings",
            f"- Animation scales (window / transition / animator): `{settings['window_animation_scale']}` / `{settings['transition_animation_scale']}` / `{settings['animator_duration_scale']}`",
            f"- Private DNS: mode=`{settings['private_dns_mode']}`, specifier=`{settings['private_dns_specifier']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 1 read-only diagnostic audit for Android devices.")
    parser.add_argument("--serial", help="Target ADB device serial (or set ADB_SERIAL).")
    parser.add_argument("--output", type=Path, help="Optional JSON output path (defaults to logs/latest_audit.json).")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown summary.")
    parser.add_argument("--summary", action="store_true", help="Print Markdown summary to stdout.")
    args = parser.parse_args()

    ensure_dirs()
    try:
        audit = collect_audit(serial=args.serial)
    except AdbDeviceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    ts = audit["audited_at"].replace(":", "").replace("-", "")
    timestamped_path = LOGS_DIR / f"device_audit_{ts}.json"
    latest_path = args.output or (LOGS_DIR / "latest_audit.json")
    payload = json.dumps(audit, indent=2) + "\n"
    timestamped_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")

    if args.json:
        print(payload, end="")
    else:
        print(format_summary_markdown(audit), end="")
        print(f"\nSaved audit snapshot to `{timestamped_path}` and `{latest_path}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
