#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")" && pwd)
source "$repo/scripts/unitree_sdk2.sh"
select_unitree_sdk2
exec "${ANAKIN_PYTHON:-/usr/bin/python3}" "$repo/scripts/run.py" "$@"
