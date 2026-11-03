# AnakinC

Anakin 部署版本的统一管理仓库。三个 Git submodule 固定一组经过验证的 SDK、执行环境和模型控制器提交；每个子仓可独立配置、编译、安装和运行，父仓负责初始化、构建顺序和联合启动。

首版支持 Ubuntu 22.04 x86_64、ROS 2 Humble。使用原生 CMake，保留 ROS 2/ament 接口与运行通信。

## 快速开始

```sh
git clone https://github.com/zdYukino/AnakinC.git
cd AnakinC
./boostup.sh
./build.sh --test
./em_run.sh
```

`boostup.sh` 按父仓锁定的提交初始化 submodule、检查系统依赖，并下载和校验官方 ONNX Runtime 1.20.1。再次执行会复用已校验依赖；有未提交子仓改动时停止，干净子仓则更新到部署锁。无需 `git submodule update --remote`。

`em_run.sh` 默认启动仿真模式的 ENV + MC，**官方模拟器需要单独启动**。SDK 是接口库，无需启动。默认键盘输入需要本地终端或 `ssh -t`。MC 后台运行，ENV 保留前台交互；Ctrl+C、SIGTERM 或任一组件退出都会清理本次启动的两个进程。

```sh
./build.sh mc --jobs 4 --test           # SDK → MC
./build.sh env --build-type Release    # SDK → ENV
./build.sh sdk                         # 只构建 SDK
./em_run.sh --dry-run                  # 检查安装并显示命令，不启动节点
./em_run.sh --sim --input gamepad
./em_run.sh --real --input remote --config /absolute/path/robot-real.yaml
```

实机配置的 `transport.interface` 必须明确指定机器人网卡。主启动器读取所选安装或 `--config` 的 `transport.ros_domain`，保证 MC 与 ENV 一致；SDK DDS domain 与 ROS domain 是两套编号。默认仿真使用 SDK `lo/domain 31`、ROS `domain 87`。

例如外部 Unitree MuJoCo 使用对应的 G1 29 自由度场景：

```sh
/path/to/unitree_mujoco/simulate/build/unitree_mujoco \
  -r g1 -i 31 -n lo -t 1 \
  -s /path/to/unitree_mujoco/unitree_robots/g1/scene_29dof.xml
```

模拟器的安装、启动、摆正与 reset 由用户管理。ENV 键位、状态和实机操作见 [独立运行说明](anakin_env/docs/standalone-operation.md)。

## 目录与独立使用

```text
AnakinC/
├── boostup.sh / build.sh / em_run.sh
├── scripts/                 # 初始化检查和联合启动实现
├── tests/                   # 使用假子进程的编排回归
├── anakin_sdk/              # submodule；消息、服务和合同
├── anakin_env/              # submodule；执行、输入与 SDK 通信
└── anakin_mc/               # submodule；推理、默认模型与 .deps/ORT
```

每个子仓的原生 CMake 产物位于 `build/子仓名/`，安装位于 `install/子仓名/`，构建日志位于 `log/`。ROS 日志也位于对应子仓；联合启动时 MC 输出写入 `anakin_mc/log/run-*/console.log`，ENV 输出保留在终端。主仓根目录不会生成 `build/`、`install/`、`log/`。

单仓不需要 AnakinC 的脚本：

```sh
/path/to/anakin_sdk/build.sh
ANAKIN_SDK_PREFIX=/path/to/anakin_sdk/install/anakin_sdk /path/to/anakin_env/build.sh --test
python3 /path/to/anakin_mc/scripts/setup_ort.py
ANAKIN_SDK_PREFIX=/path/to/anakin_sdk/install/anakin_sdk /path/to/anakin_mc/build.sh --test

ANAKIN_SDK_PREFIX=/path/to/anakin_sdk/install/anakin_sdk /path/to/anakin_env/em_run.sh --sim
ANAKIN_SDK_PREFIX=/path/to/anakin_sdk/install/anakin_sdk /path/to/anakin_mc/em_run.sh
```

ENV 单独入口沿用默认 `real`；父仓联合入口默认 `sim`。单仓默认使用相邻 `../anakin_sdk/install/anakin_sdk`，从自己的安装目录运行；正常构建和启动不引用旧 `anakin_cpp_ws` 或研究仓 `Anakin/assets`。

## 系统依赖与覆盖

初始化只检查系统依赖，不执行 sudo。需要先配置 ROS 2 Humble 软件源并安装开发依赖，例如：

```sh
sudo apt install build-essential cmake git python3 python3-yaml \
  libyaml-cpp-dev libsdl2-dev libx11-dev \
  ros-humble-ros-base ros-humble-rosidl-default-generators \
  ros-humble-common-interfaces ros-humble-unique-identifier-msgs \
  ros-humble-rmw-fastrtps-cpp
```

另外安装 Unitree SDK2，包含其头文件、CMake package 和 Cyclone DDS 动态库。CMake 要求 3.19+；ROS 接口生成默认使用系统 `/usr/bin/python3`。

| 变量 | 用途 / 默认 |
| --- | --- |
| `ROS_PREFIX` | ROS 安装；`/opt/ros/${ROS_DISTRO:-humble}` |
| `UNITREE_SDK2_PREFIX` | Unitree SDK2 完整安装前缀；`/usr/local` |
| `ANAKIN_PYTHON` | 包含 ROS 生成依赖及 PyYAML 的 Python；`/usr/bin/python3` |
| `ANAKIN_BUILD_JOBS` | 编译并行数；8，也可用 `--jobs` |
| `ANAKIN_SDK_PREFIX` | 单仓构建/运行和联合启动选择 SDK；父构建固定使用本仓 SDK |
| `ANAKIN_ENV_PREFIX` / `ANAKIN_MC_PREFIX` | 联合启动显式选择两个安装前缀 |
| `ANAKIN_PREFIX` | 单仓启动时选择该包安装；联合启动使用上面两个专用变量 |
| `ONNXRUNTIME_ROOT` | 自备 ORT 1.20.1；默认 `anakin_mc/.deps/onnxruntime-linux-x64-1.20.1` |
| `ANAKIN_ASSETS` | 覆盖 MC 模型资源根目录，保留原模型目录结构 |
| `ANAKIN_LOCO_MODEL` / `ANAKIN_MIMIC_MODEL` | 分别覆盖两个 ONNX 文件 |

MC 自带默认模型并将其安装到 `share/anakin_mc/assets/`。ORT 从固定官方 NuGet 归档提取原生库、头文件与许可证，校验 SHA256；下载缓存与解压产物均在 MC 的 `.deps/`。离线初始化可使用：

```sh
./boostup.sh --ort-archive /path/to/microsoft.ml.onnxruntime.1.20.1.nupkg
```

显式 `ONNXRUNTIME_ROOT` 只校验并使用，不自动覆盖或下载到指定目录。额外 ROS 参数逐 token 传递，例如：

```sh
./em_run.sh --env-ros-arg=-p --env-ros-arg=use_sim_time:=false \
  --mc-ros-arg=-p --mc-ros-arg=use_sim_time:=false
```

## 版本更新与验证

父仓 gitlink 是部署版本的唯一选择；`.gitmodules` 的 URL 指向三个独立远端。初始化不追踪远端最新分支。更新时在对应子仓分支提交和测试，先发布子仓提交，再提交父仓 gitlink。

SDK 的安装元数据记录其实际 Git HEAD。修改 SDK 时先提交 SDK，将最终提交写入 ENV/MC 的 `anakin_sdk.revision`，再成套重建和验证；旧产物会被启动器拒绝。即便仅修改 SDK 文档或构建脚本，也需要更新锁。

```sh
./build.sh --test
/usr/bin/python3 tests/orchestration.py
```

离线检查包括现有 C++ 合同、配置、输入和安装测试，以及假子进程的 TTY、信号、退出清理与参数传递；不启动实际 ENV/MC、ROS/DDS、模拟器或机器人。实际仿真和实机行为由使用者另行验收。

原 workspace 同级项目与旧 `anakin_cpp_ws` 保留原状。ENV 原有未提交 UI 不在本部署基线内。子仓历史集成测试/检查点可能保留旧路径，属于历史或显式开发工具。

本次构建、离线检查与运行边界见 [部署基线验证](docs/validation.md)。
