# 部署基线验证

验证环境：Ubuntu 22.04.5 x86_64、ROS 2 Humble、GNU C++ 11.4、CMake 3.31.10、Python 3.10。

本次固定的子仓提交：

| 子仓 | 提交 |
| --- | --- |
| anakin_sdk | `44e140b73fd50fb6e77f47ab71dc5399b8dfaec1` |
| anakin_env | `13b8fe56f4b4bce26eb4c2c0b4f978aafabcec12` |
| anakin_mc | `25f43b325eaa7238d26ece4f42fd66909d4ba726` |

已执行：

- `./build.sh --test --jobs 8`：三个项目分别配置、编译并安装，ENV 21/21、MC 2/2 离线测试通过。
- `/usr/bin/python3 tests/orchestration.py`：SDK → 指定组件的顺序、无关子仓缺失、配置失败传播、独立产物目录、参数和空格路径、YAML domain、安装预检、TTY、SIGINT/SIGTERM、组件退出及强制终止后的终端恢复均通过。仅使用假子进程。
- `./em_run.sh --dry-run`：真实安装前缀、SDK 版本锁、默认模型和 ORT 预检通过，默认 sim/domain 87；没有启动原生节点。
- 安装后的 `anakin_env_config_test --installed`：安装资源及配置解析通过。
- ORT 在全新临时目录中从官方 URL 下载、校验 SHA256、解压、重复初始化通过；损坏的 SONAME 别名被拒绝。本地官方归档复用和 `setup_ort.py --check` 也通过。
- 两个打包模型的 SHA256 与既有数值参考一致；主仓根目录没有 build/install/log/logs，构建和运行产物归各子仓所有。

SDL 离线测试在受限沙箱内的最后一次 SDL 子系统清理阶段段错误，新旧二进制及独立最小复现均出现相同现象；沙箱外测试完整通过。本次没有跳过测试或为此修改业务代码。

本次没有启动真实 ENV/MC ROS/DDS 节点、官方模拟器或机器人。实际仿真与实机行为尚需使用者在对应环境验收。原 workspace 下三个项目的工作树和未提交 UI 保持原状。
