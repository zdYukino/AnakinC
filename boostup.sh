#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")" && pwd)
archive=()
if (( $# )); then
 case "$1" in
  --help|-h)
   echo 'Usage: ./boostup.sh [--ort-archive /path/to/microsoft.ml.onnxruntime.1.20.1.nupkg]'
   echo 'Initialize pinned submodules, check system dependencies, and prepare verified ORT.'
   exit 0 ;;
  --ort-archive)
   [[ $# == 2 && -f $2 ]] || { echo '--ort-archive requires an existing file' >&2; exit 2; }
   archive=(--archive "$(realpath -e -- "$2")") ;;
  *) echo 'Unknown option; see ./boostup.sh --help' >&2; exit 2 ;;
 esac
fi
# Refuse conflicted or dirty submodules; clean checkouts follow the deployment lock.
while IFS= read -r line; do
 case "${line:0:1}" in
  U) echo "Submodule has a merge conflict: $line" >&2; exit 2 ;;
 esac
done < <(git -C "$repo" submodule status --recursive)
for package in anakin_sdk anakin_env anakin_mc unitree_mujoco; do
 if [[ -e "$repo/$package/.git" && -n $(git -C "$repo/$package" status --porcelain --untracked-files=normal) ]]; then
  echo "$package has local changes; preserve them before initialization." >&2; exit 2
 fi
done
git -C "$repo" submodule sync --recursive
git -C "$repo" submodule update --init --recursive
python=${ANAKIN_PYTHON:-/usr/bin/python3}
"$python" "$repo/scripts/check_dependencies.py"
"$python" "$repo/anakin_mc/scripts/setup_ort.py" "${archive[@]}"
echo 'Initialization complete. Run ./build.sh --test, then ./em_run.sh.'
