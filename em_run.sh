#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")" && pwd)
exec "${ANAKIN_PYTHON:-/usr/bin/python3}" "$repo/scripts/run.py" "$@"
