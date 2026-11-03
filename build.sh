#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")" && pwd)
target=all
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
 cat <<'EOF'
Usage: ./build.sh [all|sdk|env|mc] [--jobs N] [--build-type TYPE] [--test] [-- CMake options]
Build SDK first, then each selected component with its own native CMake script.
All outputs and logs remain inside the corresponding submodule.
EOF
 exit 0
fi
if [[ $# -gt 0 && $1 != -* ]]; then target=$1; shift; fi
packages=(anakin_sdk)
case "$target" in
 all) packages+=(anakin_env anakin_mc) ;;
 env|mc) packages+=("anakin_$target") ;;
 sdk) ;;
 *) echo "Unknown target: $target" >&2; exit 2 ;;
esac
for package in "${packages[@]}"; do
 [[ -x "$repo/$package/build.sh" ]] || { echo "Missing $package; run ./boostup.sh first." >&2; exit 2; }
done
export ANAKIN_SDK_PREFIX="$repo/anakin_sdk/install/anakin_sdk"
for package in "${packages[@]}"; do "$repo/$package/build.sh" "$@"; done
