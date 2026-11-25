"""Stage 5: Before/After Android benchmarking and Markdown optimization report generator."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import (  # noqa: E402
    LOGS_DIR,
    AdbDeviceError,
    ensure_dirs,
    run_adb_shell,
    utc_now_iso,
    validate_package_name,
)
from audit_device import parse_meminfo_summary  # noqa: E402

BEFORE_PATH = LOGS_DIR / "benchmark_before.json"
AFTER_PATH = LOGS_DIR / "benchmark_after.json"
REPORT_PATH = LOGS_DIR / "optimization_report.md"


def parse_ram_kb(ram_line: str | None) -> int | None:
    """Extract numeric kilobytes from a `dumpsys meminfo` summary line."""
    if not ram_line:
        return None
    match = re.search(r"([\d,]+)K", ram_line)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def count_active_services(raw_services: str) -> int:
    """Count `ServiceRecord{...}` entries in `dumpsys activity services`."""
    return len(re.findall(r"ServiceRecord\{", raw_services))


def parse_total_time_ms(am_start_output: str) -> int | None:
    """Parse `TotalTime: <ms>` (or fallback `WaitTime: <ms>` on trampolines) from `am start -W`."""
    total_match = re.search(r"TotalTime:\s*(\d+)", am_start_output)
    if total_match:
        return int(total_match.group(1))
    wait_match = re.search(r"WaitTime:\s*(\d+)", am_start_output)
    return int(wait_match.group(1)) if wait_match else None


def resolve_main_component(pkg: str, serial: str | None = None) -> str | None:
    """Resolve the launchable `pkg/activity` component using `cmd package resolve-activity`."""
    out = run_adb_shell(
        ["cmd", "package", "resolve-activity", "--brief", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", pkg],
        serial=serial,
        check=False,
    )
    for line in reversed(out.splitlines()):
        cleaned = line.strip()
        if "/" in cleaned and not cleaned.startswith("priority="):
            return cleaned
    return None


def measure_cold_start_ms(pkg: str, serial: str | None = None) -> dict[str, Any]:
    """Force-stop `pkg` and measure cold-start `TotalTime` (ms) via `am start -W`."""
    pkg = validate_package_name(pkg)
    component = resolve_main_component(pkg, serial=serial)
    if not component:
        return {"package": pkg, "component": None, "total_time_ms": None, "error": "No launcher activity found"}

    run_adb_shell(["am", "force-stop", pkg], serial=serial, check=False)
    time.sleep(0.5)
    out = run_adb_shell(["am", "start", "-W", component], serial=serial, check=False, timeout=30)
    total_ms = parse_total_time_ms(out)
    return {
        "package": pkg,
        "component": component,
        "total_time_ms": total_ms,
        "error": None if total_ms is not None else f"Could not parse TotalTime from output: {out.strip()}",
    }


def count_frozen_processes(raw_activity: str) -> int:
    """Count frozen process indicators in `dumpsys activity` output."""
    return len(re.findall(r"\bfrozen=true\b|\bApps frozen:", raw_activity))


def collect_benchmark(packages: list[str], serial: str | None = None) -> dict[str, Any]:
    """Capture RAM summary, background service count, frozen process count, and cold-start timings."""
    meminfo_raw = run_adb_shell(["dumpsys", "meminfo"], serial=serial, check=False, timeout=90)
    mem_summary = parse_meminfo_summary(meminfo_raw)
    services_raw = run_adb_shell(["dumpsys", "activity", "services"], serial=serial, check=False, timeout=90)
    activity_raw = run_adb_shell(["dumpsys", "activity"], serial=serial, check=False, timeout=90)

    launches = [measure_cold_start_ms(pkg, serial=serial) for pkg in packages]
    return {
        "captured_at": utc_now_iso(),
        "total_ram_kb": parse_ram_kb(mem_summary.get("total_ram")),
        "used_ram_kb": parse_ram_kb(mem_summary.get("used_ram")),
        "free_ram_kb": parse_ram_kb(mem_summary.get("free_ram")),
        "active_service_records": count_active_services(services_raw),
        "frozen_indicators": count_frozen_processes(activity_raw),
        "cold_starts": launches,
    }


def render_comparison_report(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Generate a Markdown before-vs-after optimization report."""
    def fmt_kb_mb(val: int | None) -> str:
        return f"{val / 1024:.1f} MB (`{val}` KB)" if val is not None else "N/A"

    def delta_str(b: int | None, a: int | None, unit: str = "", lower_is_better: bool = True) -> str:
        if b is None or a is None:
            return "N/A"
        diff = a - b
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff}{unit}"

    lines = [
        "# Android Optimization Verification Report",
        "",
        f"- **Before Snapshot**: `{before.get('captured_at')}`",
        f"- **After Snapshot**: `{after.get('captured_at')}`",
        "",
        "## System Metrics Comparison",
        "",
        "| Metric | Before | After | Delta |",
        "| :--- | :--- | :--- | :--- |",
        f"| Free RAM | {fmt_kb_mb(before.get('free_ram_kb'))} | {fmt_kb_mb(after.get('free_ram_kb'))} | {delta_str(before.get('free_ram_kb'), after.get('free_ram_kb'), ' KB', lower_is_better=False)} |",
        f"| Used RAM | {fmt_kb_mb(before.get('used_ram_kb'))} | {fmt_kb_mb(after.get('used_ram_kb'))} | {delta_str(before.get('used_ram_kb'), after.get('used_ram_kb'), ' KB')} |",
        f"| Active Service Records | `{before.get('active_service_records')}` | `{after.get('active_service_records')}` | {delta_str(before.get('active_service_records'), after.get('active_service_records'))} |",
        "",
        "## App Cold-Start Launch Latency (`am start -W` TotalTime)",
        "",
        "| Package | Before (ms) | After (ms) | Delta (ms) |",
        "| :--- | :--- | :--- | :--- |",
    ]

    before_map = {item["package"]: item for item in before.get("cold_starts", [])}
    after_map = {item["package"]: item for item in after.get("cold_starts", [])}
    all_pkgs = list(dict.fromkeys([*before_map.keys(), *after_map.keys()]))
    for pkg in all_pkgs:
        b_ms = (before_map.get(pkg) or {}).get("total_time_ms")
        a_ms = (after_map.get(pkg) or {}).get("total_time_ms")
        lines.append(f"| `{pkg}` | `{b_ms}` | `{a_ms}` | {delta_str(b_ms, a_ms, ' ms')} |")

    if not all_pkgs:
        lines.append("| _(none measured)_ | - | - | - |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 5: Before/After benchmark and Markdown report.")
    parser.add_argument("--phase", choices=("before", "after", "compare"), default="after")
    parser.add_argument("--packages", nargs="*", default=[], help="Up to 3-5 packages for cold-start timing.")
    parser.add_argument("--serial", help="Target ADB device serial.")
    args = parser.parse_args()

    ensure_dirs()
    try:
        if args.phase == "before":
            data = collect_benchmark(args.packages, serial=args.serial)
            BEFORE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"Saved baseline benchmark to `{BEFORE_PATH}`.")
            return 0

        if args.phase == "after":
            pkgs = args.packages
            if not pkgs and BEFORE_PATH.exists():
                prev = json.loads(BEFORE_PATH.read_text(encoding="utf-8"))
                pkgs = [item["package"] for item in prev.get("cold_starts", [])]
            data = collect_benchmark(pkgs, serial=args.serial)
            AFTER_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"Saved post-optimization benchmark to `{AFTER_PATH}`.")
            if BEFORE_PATH.exists():
                before = json.loads(BEFORE_PATH.read_text(encoding="utf-8"))
                report = render_comparison_report(before, data)
                REPORT_PATH.write_text(report, encoding="utf-8")
                print(report)
                print(f"Saved comparison report to `{REPORT_PATH}`.")
            return 0

        # compare
        if not BEFORE_PATH.exists() or not AFTER_PATH.exists():
            print("ERROR: Both `logs/benchmark_before.json` and `logs/benchmark_after.json` are required.", file=sys.stderr)
            return 1
        before = json.loads(BEFORE_PATH.read_text(encoding="utf-8"))
        after = json.loads(AFTER_PATH.read_text(encoding="utf-8"))
        report = render_comparison_report(before, after)
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(report)
        return 0
    except (ValueError, AdbDeviceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
