"""Sync and locally cache the UAD-NG (Universal Android Debloater Next Generation) database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adb_common import CACHE_DIR, UAD_CACHE_PATH, ensure_dirs, utc_now_iso  # noqa: E402

DEFAULT_UAD_URL = (
    "https://raw.githubusercontent.com/Universal-Debloater-Alliance/"
    "universal-android-debloater-next-generation/main/resources/assets/uad_lists.json"
)
UAD_META_PATH = CACHE_DIR / "uad_metadata.json"


def normalize_uad_database(raw_data: object) -> dict[str, dict[str, object]]:
    """Normalize UAD-NG JSON (object keyed by pkg ID OR legacy list of dicts) into `{pkg: entry}`."""
    normalized: dict[str, dict[str, object]] = {}

    if isinstance(raw_data, dict):
        for pkg_id, entry in raw_data.items():
            if not isinstance(pkg_id, str) or not isinstance(entry, dict):
                continue
            normalized[pkg_id.strip()] = {
                "id": pkg_id.strip(),
                "list": str(entry.get("list") or "Misc"),
                "description": str(entry.get("description") or "").strip(),
                "removal": str(entry.get("removal") or "Unknown").strip().capitalize(),
                "dependencies": entry.get("dependencies") or [],
                "neededBy": entry.get("neededBy") or [],
                "labels": entry.get("labels") or [],
                "warning": entry.get("warning"),
            }
        return normalized

    if isinstance(raw_data, list):
        for entry in raw_data:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            pkg_id = str(entry["id"]).strip()
            normalized[pkg_id] = {
                "id": pkg_id,
                "list": str(entry.get("list") or "Misc"),
                "description": str(entry.get("description") or "").strip(),
                "removal": str(entry.get("removal") or "Unknown").strip().capitalize(),
                "dependencies": entry.get("dependencies") or [],
                "neededBy": entry.get("neededBy") or [],
                "labels": entry.get("labels") or [],
                "warning": entry.get("warning"),
            }
        return normalized

    raise ValueError("Unsupported UAD-NG JSON root type; expected object or array.")


def sync_uad(url: str = DEFAULT_UAD_URL, force: bool = False, local_file: Path | None = None) -> dict[str, object]:
    """Download (or load from local file) and cache `uad_lists.json` under `cache/`."""
    ensure_dirs()
    if UAD_CACHE_PATH.exists() and not force and not local_file:
        existing = normalize_uad_database(json.loads(UAD_CACHE_PATH.read_text(encoding="utf-8")))
        return {
            "source": "cache",
            "path": str(UAD_CACHE_PATH),
            "package_count": len(existing),
        }

    if local_file:
        raw_bytes = local_file.read_bytes()
        source = str(local_file)
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "android-ai-optimizer/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw_bytes = resp.read()
        source = url

    parsed = json.loads(raw_bytes.decode("utf-8"))
    normalized = normalize_uad_database(parsed)

    tmp_path = UAD_CACHE_PATH.with_suffix(".json.tmp")
    tmp_path.write_bytes(raw_bytes)
    tmp_path.replace(UAD_CACHE_PATH)

    meta = {
        "synced_at": utc_now_iso(),
        "source": source,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "package_count": len(normalized),
    }
    UAD_META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {"source": source, "path": str(UAD_CACHE_PATH), "package_count": len(normalized)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and cache UAD-NG package lists (uad_lists.json).")
    parser.add_argument("--url", default=DEFAULT_UAD_URL, help="Override raw uad_lists.json URL.")
    parser.add_argument("--local-file", type=Path, help="Import uad_lists.json from a local file path.")
    parser.add_argument("--force", action="store_true", help="Re-download even if cache/uad_lists.json exists.")
    args = parser.parse_args()

    try:
        info = sync_uad(url=args.url, force=args.force, local_file=args.local_file)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"ERROR: Failed to sync UAD-NG database: {exc}", file=sys.stderr)
        return 1

    print(
        f"UAD-NG database ready ({info['package_count']} packages) at `{info['path']}` "
        f"(source: {info['source']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
