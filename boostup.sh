#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")" && pwd)
archive=()
if (( $# )); then
 case "$1" in
  --help|-h)
   echo 'Usage: ./boostup.sh [--ort-archive /path/to/microsoft.ml.onnxruntime.1.20.1.nupkg]'
   echo 'Initialize submodules, prepare Unitree SDK2 if needed, check dependencies, and prepare ORT.'
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
source "$repo/scripts/unitree_sdk2.sh"
select_unitree_sdk2
if [[ -z ${UNITREE_SDK2_PREFIX:-} ]] && ! unitree_sdk2_present "/usr/local"; then
 source_dir="$repo/thirdparty/unitree_sdk2"
 build_dir="$repo/thirdparty/unitree_sdk2-build"
 install_dir="$repo/thirdparty/unitree_sdk2-install"
 mkdir -p -- "$repo/thirdparty"
 if [[ ! -e "$source_dir" ]]; then
  # Clone into a temporary directory so an interrupted clone can be retried.
  clone_dir=$(mktemp -d "$repo/thirdparty/.unitree-sdk2-clone.XXXXXX")
  trap 'rm -rf -- "$clone_dir"' EXIT
  git clone https://github.com/unitreerobotics/unitree_sdk2.git "$clone_dir"
  mv -- "$clone_dir" "$source_dir"
  trap - EXIT
 elif [[ ! -f "$source_dir/CMakeLists.txt" ]]; then
  echo "Existing SDK source directory is incomplete: $source_dir" >&2; exit 2
 fi
 echo "Installing Unitree SDK2 under $install_dir"
 cmake -S "$source_dir" -B "$build_dir" -DCMAKE_INSTALL_PREFIX="$install_dir" -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_EXAMPLES=OFF
 cmake --build "$build_dir" --parallel "${ANAKIN_BUILD_JOBS:-8}"
 cmake --install "$build_dir"
 unitree_sdk2_present "$install_dir" || { echo "Unitree SDK2 installation failed: $install_dir" >&2; exit 2; }
 export UNITREE_SDK2_PREFIX="$install_dir"
fi
python=${ANAKIN_PYTHON:-/usr/bin/python3}
"$python" "$repo/scripts/check_dependencies.py"
"$python" "$repo/anakin_mc/scripts/setup_ort.py" "${archive[@]}"
echo 'Initialization complete. Run ./build.sh --test, then ./em_run.sh.'
