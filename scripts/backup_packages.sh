#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOGS_DIR="${REPO_ROOT}/logs"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${SCRIPT_DIR}/backup_packages.py" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "${SCRIPT_DIR}/backup_packages.py" "$@"
fi

# Pure POSIX + adb fallback if Python is unavailable
if ! command -v adb >/dev/null 2>&1; then
  echo "ERROR: Neither python3/python nor adb was found on PATH." >&2
  exit 1
fi

SERIAL_ARGS=()
if [[ -n "${ADB_SERIAL:-}" ]]; then
  SERIAL_ARGS=(-s "${ADB_SERIAL}")
elif [[ "${1:-}" == "--serial" && -n "${2:-}" ]]; then
  SERIAL_ARGS=(-s "$2")
fi

mkdir -p "${LOGS_DIR}"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

{
  echo "# Android AI Optimizer Package Snapshot (${TS})"
  echo "# === ALL PACKAGES ==="
  adb "${SERIAL_ARGS[@]}" shell pm list packages
  echo ""
  echo "# === ENABLED PACKAGES ==="
  adb "${SERIAL_ARGS[@]}" shell pm list packages -e
  echo ""
  echo "# === DISABLED PACKAGES ==="
  adb "${SERIAL_ARGS[@]}" shell pm list packages -d
} > "${LOGS_DIR}/packages_backup.txt"

{
  echo "# Android AI Optimizer Settings Snapshot (${TS})"
  echo "# === GLOBAL ==="
  adb "${SERIAL_ARGS[@]}" shell settings list global || true
  echo ""
  echo "# === SYSTEM ==="
  adb "${SERIAL_ARGS[@]}" shell settings list system || true
  echo ""
  echo "# === SECURE ==="
  adb "${SERIAL_ARGS[@]}" shell settings list secure || true
} > "${LOGS_DIR}/settings_backup.txt"

touch "${LOGS_DIR}/removed_packages.txt"
echo "Backup written to ${LOGS_DIR}/packages_backup.txt and ${LOGS_DIR}/settings_backup.txt"
