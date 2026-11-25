#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REMOVED_LOG="${REPO_ROOT}/logs/removed_packages.txt"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${SCRIPT_DIR}/restore_package.py" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "${SCRIPT_DIR}/restore_package.py" "$@"
fi

if ! command -v adb >/dev/null 2>&1; then
  echo "ERROR: Neither python3/python nor adb was found on PATH." >&2
  exit 1
fi

if [[ "${1:-}" == "--all" ]]; then
  if [[ ! -f "${REMOVED_LOG}" ]]; then
    echo "No ${REMOVED_LOG} found."
    exit 0
  fi
  while IFS= read -r pkg; do
    [[ -z "${pkg}" || "${pkg}" == \#* ]] && continue
    echo "Restoring ${pkg}..."
    adb shell cmd package install-existing "${pkg}"
  done < "${REMOVED_LOG}"
elif [[ -n "${1:-}" ]]; then
  adb shell cmd package install-existing "$1"
else
  echo "Usage: $0 <package_name> | --all" >&2
  exit 1
fi
