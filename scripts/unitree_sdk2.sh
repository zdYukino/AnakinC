#!/usr/bin/env bash
# Select a repository-local SDK only when no explicit or system SDK is present.
unitree_sdk2_present() {
 [[ -f "$1/lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake" || -f "$1/lib64/cmake/unitree_sdk2/unitree_sdk2Config.cmake" ]]
}
select_unitree_sdk2() {
 if [[ -z ${UNITREE_SDK2_PREFIX:-} ]] && ! unitree_sdk2_present "/usr/local" && unitree_sdk2_present "$repo/thirdparty/unitree_sdk2-install"; then
  export UNITREE_SDK2_PREFIX="$repo/thirdparty/unitree_sdk2-install"
 fi
}
