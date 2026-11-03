#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")" && pwd)
exec "$repo/anakin_env/ui/em_run.sh" "$@"
