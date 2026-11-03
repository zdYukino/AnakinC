"""Supervise the simulator, UI, and installed ENV and MC."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import re

ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path):
    try:
        import yaml
    except ImportError as error:
        raise ValueError("Install python3-yaml; see README.md") from error

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError(f"YAML mapping keys must be strings: {path}")
            if key in result:
                raise ValueError(f"Duplicate YAML key {key!r} in {path}")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        result = yaml.load(path.read_text(), Loader=UniqueLoader)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid YAML {path}: {error}") from error
    if not isinstance(result, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return result


def parse_arguments():
    parser = argparse.ArgumentParser(description="Start G1 simulation, ENV, MC and UI (default); --real omits simulation.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--sim", action="store_true", help="simulation mode (default)")
    modes.add_argument("--real", action="store_true", help="real robot mode")
    parser.add_argument("--real-checks", action="store_true",
                        help="in simulation, use real state/guard rules with simulated authority")
    parser.add_argument("--real-config", type=Path, help="real-mode rules for --real-checks")
    parser.add_argument("--config", type=Path, help="ENV mode YAML")
    parser.add_argument("--input-config", type=Path, help="ENV input YAML")
    parser.add_argument("--input", choices=("auto", "web", "gamepad", "remote"))
    parser.add_argument("--no-simulator", action="store_true", help="use an already running simulator")
    parser.add_argument("--no-ui", action="store_true", help="do not start the telemetry UI")
    parser.add_argument("--env-ros-arg", action="append", default=[], metavar="TOKEN",
                        help="repeat for each ENV ROS token; use --env-ros-arg=-p for flags")
    parser.add_argument("--mc-ros-arg", action="append", default=[], metavar="TOKEN",
                        help="repeat for each MC ROS token; MC already supplies --ros-args")
    parser.add_argument("--dry-run", action="store_true", help="check installations and print commands without starting nodes")
    return parser.parse_args()


def prepare(args):
    mode = "real" if args.real else "sim"
    if args.real_checks and mode != "sim":
        raise ValueError("--real-checks requires simulation mode")
    if args.real_config and not args.real_checks:
        raise ValueError("--real-config requires --real-checks")
    sdk_prefix = Path(os.environ.get("ANAKIN_SDK_PREFIX") or ROOT / "anakin_sdk/install/anakin_sdk").resolve()
    env_prefix = Path(os.environ.get("ANAKIN_ENV_PREFIX") or ROOT / "anakin_env/install/anakin_env").resolve()
    mc_prefix = Path(os.environ.get("ANAKIN_MC_PREFIX") or ROOT / "anakin_mc/install/anakin_mc").resolve()
    resources = env_prefix / "share/anakin_env/config"
    config = (args.config or resources / f"{mode}.yaml").resolve()
    data = read_yaml(config)
    if data.get("mode") != mode:
        raise ValueError(f"Selected {mode} mode differs from YAML mode: {config}")
    real_config = None
    if args.real_checks:
        real_config = (args.real_config or resources / "real.yaml").resolve()
        if read_yaml(real_config).get("mode") != "real":
            raise ValueError(f"Real checks require mode: real in {real_config}")
    transport = data.get("transport")
    if args.real_checks and (not isinstance(transport, dict) or transport.get("interface", "lo") != "lo" or
                             type(transport.get("sdk_domain", 31)) is not int or
                             not 1 <= transport.get("sdk_domain", 31) <= 232):
        raise ValueError("--real-checks requires simulation interface lo and a nonzero SDK domain")
    domain = transport.get("ros_domain") if isinstance(transport, dict) else None
    if isinstance(domain, str) and re.fullmatch(r"[+-]?[0-9]+", domain):
        domain = int(domain, 10)
    if type(domain) is not int or not 0 <= domain <= 232:
        raise ValueError(f"transport.ros_domain must be an integer in 0..232: {config}")
    input_path = (args.input_config or resources / "inputs.yaml").resolve()
    inputs = read_yaml(input_path)
    primary = args.input or inputs.get("primary")
    if primary not in ("auto", "web", "gamepad", "remote"):
        raise ValueError(f"Invalid primary input in {input_path}")
    env_command = [str(ROOT / "anakin_env/em_run.sh"), f"--{mode}", "--config", str(config)]
    if args.real_checks:
        env_command.append("--real-checks")
        if args.real_config:
            env_command += ["--real-config", str(real_config)]
    if args.input_config:
        env_command += ["--input-config", str(input_path)]
    if args.input:
        env_command += ["--input", args.input]
    if args.env_ros_arg:
        env_command += ["--ros-args", *args.env_ros_arg]
    mc_command = [str(ROOT / "anakin_mc/em_run.sh"), *args.mc_ros_arg]
    base = os.environ.copy()
    base.pop("ANAKIN_LAUNCH_CHECK_ONLY", None)
    base.update(ANAKIN_SDK_PREFIX=str(sdk_prefix), ROS_DOMAIN_ID=str(domain))
    environments = {
        "ENV": dict(base, ANAKIN_PREFIX=str(env_prefix)),
        "MC": dict(base, ANAKIN_PREFIX=str(mc_prefix)),
    }
    commands = {"ENV": env_command, "MC": mc_command}
    for name, command in commands.items():
        checked = subprocess.run(command, env=dict(environments[name], ANAKIN_LAUNCH_CHECK_ONLY="1"),
                                 stdin=subprocess.DEVNULL, check=False)
        if checked.returncode:
            raise ValueError(f"{name} installation preflight failed; build the locked version first")
    if mode == "sim" and not args.no_simulator:
        simulator = ROOT / "unitree_mujoco/simulate/build/unitree_mujoco"
        scene = ROOT / "unitree_mujoco/unitree_robots/g1/scene_29dof.xml"
        if not os.access(simulator, os.X_OK) or not scene.is_file():
            raise ValueError("Simulator not built or missing; see README.md for Unitree MuJoCo build instructions")
        sdk_domain = transport.get("sdk_domain", 31)
        interface = transport.get("interface", "lo")
        if type(sdk_domain) is not int or not 0 <= sdk_domain <= 232 or not isinstance(interface, str) or not interface:
            raise ValueError(f"Invalid simulator SDK domain or interface: {config}")
        commands["SIM"] = [str(simulator), "-r", "g1", "-i", str(sdk_domain), "-n", interface, "-t", "1", "-s", str(scene)]
        environments["SIM"] = base.copy()
    if not args.no_ui:
        ui = ROOT / "ui.sh"
        setup = sdk_prefix / "share/anakin_sdk/local_setup.bash"
        if not os.access(ui, os.X_OK) or not setup.is_file():
            raise ValueError("UI launcher or SDK ROS setup missing; initialize and build first")
        commands["UI"] = [str(ui), "--domain", str(domain), "--ros-setup", str(setup)]
        environments["UI"] = base.copy()
    return commands, environments, mode, domain


def stop(children):
    # Only Popen-owned children are signaled. Poll/reap before signaling prevents PID reuse.
    for signum, timeout in ((signal.SIGINT, 2.0), (signal.SIGTERM, 2.0), (signal.SIGKILL, 1.0)):
        active = [child for child in children if child.poll() is None]
        if not active:
            break
        for child in active:
            try:
                if getattr(child, "anakin_group", False):
                    os.killpg(child.pid, signum)
                else:
                    child.send_signal(signum)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + timeout
        while any(child.poll() is None for child in active) and time.monotonic() < deadline:
            time.sleep(0.05)
    for child in children:
        child.wait()


def run(args):
    commands, environments, mode, domain = prepare(args)
    checks = ", real_checks=enabled (simulated authority)" if args.real_checks else ""
    print(f"AnakinC: mode={mode}{checks}, ROS_DOMAIN_ID={domain}", flush=True)
    if args.dry_run:
        for name, command in commands.items():
            print(f"{name}: {shlex.join(command)}")
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + f"-{os.getpid()}"
    logs = {}
    for name, package in (("ENV", "anakin_env"), ("MC", "anakin_mc")):
        directory = ROOT / package / "log" / f"run-{stamp}"
        directory.mkdir(parents=True)
        environments[name]["ROS_LOG_DIR"] = str(directory / "ros")
        logs[name] = directory
    print(f"ENV ROS logs: {logs['ENV'] / 'ros'}\nMC output: {logs['MC'] / 'console.log'}", flush=True)
    received_signal = 0

    def requested(signum, _frame):
        nonlocal received_signal
        received_signal = signum

    previous = {signum: signal.signal(signum, requested) for signum in (signal.SIGINT, signal.SIGTERM)}
    children = []
    try:
        with (logs["MC"] / "console.log").open("w") as output, \
                (logs["ENV"] / "ui.log").open("w") as ui_output, \
                (logs["ENV"] / "simulator.log").open("w") as sim_output:
            names = []
            for name, output_file in (("SIM", sim_output), ("UI", ui_output)):
                if name in commands:
                    children.append(subprocess.Popen(commands[name], env=environments[name], stdin=subprocess.DEVNULL,
                                                     stdout=output_file, stderr=subprocess.STDOUT,
                                                     cwd=ROOT / "unitree_mujoco/simulate/build" if name == "SIM" else ROOT,
                                                     start_new_session=True))
                    children[-1].anakin_group = True
                    names.append(name)
            if received_signal:
                return 128 + received_signal
            children.append(subprocess.Popen(commands["MC"], env=environments["MC"], stdin=subprocess.DEVNULL,
                                             stdout=output, stderr=subprocess.STDOUT))
            names.append("MC")
            if received_signal:
                return 128 + received_signal
            children.append(subprocess.Popen(commands["ENV"], env=environments["ENV"], stdin=subprocess.DEVNULL))
            names.append("ENV")
            if "UI" in commands:
                print(f"UI: http://127.0.0.1:8765/ (log: {logs['ENV'] / 'ui.log'})", flush=True)
            if "SIM" in commands:
                print(f"Simulator log: {logs['ENV'] / 'simulator.log'}", flush=True)
            while not received_signal:
                for name, child in zip(names, children):
                    code = child.poll()
                    if code is not None:
                        print(f"{name} exited ({code}); stopping this launch.", file=sys.stderr)
                        return code if code >= 0 else 128 - code
                time.sleep(0.05)
            return 128 + received_signal
    finally:
        try:
            stop(children)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def main():
    args = parse_arguments()
    try:
        return run(args)
    except (OSError, ValueError) as error:
        print(f"AnakinC: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
