"""Exercise deployment orchestration using fake children; never runs ROS or a robot."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
CHILD = r'''#!/usr/bin/python3
import json, os
from pathlib import Path
import signal, sys, time
role = Path(__file__).resolve().parent.name
if os.environ.get("ANAKIN_LAUNCH_CHECK_ONLY") == "1":
    sys.exit(2 if os.environ.get("TEST_PREFLIGHT_FAIL") == role else 0)
record = Path(os.environ["TEST_RECORDS"]) / (role + ".json")
record.write_text(json.dumps(dict(pid=os.getpid(), argv=sys.argv[1:],
    prefix=os.environ["ANAKIN_PREFIX"], sdk=os.environ["ANAKIN_SDK_PREFIX"],
    domain=os.environ["ROS_DOMAIN_ID"], tty=sys.stdin.isatty(),
    ros_log=os.environ["ROS_LOG_DIR"])))
stubborn = role == "anakin_env" and os.environ.get("TEST_STUBBORN") == "1"
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, (lambda *_: None) if stubborn else (lambda *_: sys.exit(0)))
if stubborn:
    record.with_suffix(".ready").touch()
code = os.environ.get("TEST_ENV_EXIT" if role == "anakin_env" else "TEST_MC_EXIT")
if code:
    time.sleep(0.3)
    sys.exit(int(code))
while True:
    time.sleep(0.05)
'''


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def fixture(root):
    (root / "scripts").mkdir()
    (root / "tests").mkdir()
    for name in ("em_run.sh", "build.sh"):
        shutil.copy2(SOURCE / name, root / name)
    shutil.copy2(SOURCE / "scripts/run.py", root / "scripts/run.py")
    for package in ("anakin_sdk", "anakin_env", "anakin_mc"):
        repo = root / package
        repo.mkdir()
        shutil.copy2(SOURCE / package / "build.sh", repo / "build.sh")
        if package != "anakin_sdk":
            (repo / "em_run.sh").write_text(CHILD)
            (repo / "em_run.sh").chmod(0o755)
    sdk = root / "anakin_sdk/install/anakin_sdk/share/anakin_sdk/cmake"
    sdk.mkdir(parents=True)
    (sdk / "anakin_sdkConfig.cmake").touch()
    (sdk.parent / "local_setup.bash").touch()
    sim = root / "unitree_mujoco/simulate/build"
    sim.mkdir(parents=True)
    scene = root / "unitree_mujoco/unitree_robots/g1/scene_29dof.xml"
    scene.parent.mkdir(parents=True)
    scene.touch()
    extra_child = '''#!/usr/bin/python3
import json, os, signal, sys, time
from pathlib import Path
name = "sim" if "unitree_mujoco" in sys.argv[0] else "ui"
(Path(os.environ["TEST_RECORDS"]) / (name + ".json")).write_text(json.dumps(dict(pid=os.getpid(), argv=sys.argv[1:])))
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True: time.sleep(0.05)
'''
    for path in (sim / "unitree_mujoco", root / "ui.sh"):
        path.write_text(extra_child)
        path.chmod(0o755)
    config = root / "anakin_env/install/anakin_env/share/anakin_env/config"
    config.mkdir(parents=True)
    (config / "sim.yaml").write_text("mode: sim\ntransport: {ros_domain: 87}\n")
    (config / "real.yaml").write_text("mode: real\ntransport: {ros_domain: 87}\n")
    (config / "inputs.yaml").write_text("primary: auto\n")
    return config


def environment(root):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("ANAKIN_", "TEST_")) and key not in
           ("ROS_PREFIX", "ROS_DISTRO", "ONNXRUNTIME_ROOT", "UNITREE_SDK2_PREFIX")}
    records = root / "records"
    records.mkdir(exist_ok=True)
    for file in records.iterdir():
        file.unlink()
    env.update(TEST_RECORDS=str(records), ANAKIN_PREFIX="/unrelated/global-prefix")
    return env


def captures(root):
    return {path.stem: json.loads(path.read_text()) for path in (root / "records").glob("*.json")}


def wait_for(root, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate(captures(root)):
                return
        except json.JSONDecodeError:
            pass
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for stub children")


def all_reaped(root):
    for data in captures(root).values():
        try:
            os.kill(data["pid"], 0)
        except ProcessLookupError:
            continue
        raise AssertionError(f"Child survived supervision: {data['pid']}")


def start(root, args, extra=None, stdin=None, full=False):
    env = environment(root)
    env.update(extra or {})
    return subprocess.Popen([str(root / "em_run.sh"), *([] if full else ["--no-simulator", "--no-ui"]), *args], cwd="/tmp", env=env,
                            stdin=stdin or subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def finish(process, root, expected):
    try:
        out, err = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise AssertionError("Supervisor did not exit within cleanup deadline")
    require(process.returncode == expected, f"Expected {expected}, got {process.returncode}: {out} {err}")
    all_reaped(root)
    return out, err


def check_runtime(root, config):
    process = start(root, ["--dry-run"])
    out, _ = finish(process, root, 0)
    require("--sim" in out and not captures(root), "Dry run must not start a node")
    require(not (root / "anakin_mc/log").exists(), "Dry run must not generate run logs")
    process = start(root, ["--input", "remote"], full=True)
    try:
        wait_for(root, lambda rows: len(rows) == 4)
        rows = captures(root)
        require(rows["sim"]["argv"][:8] == ["-r", "g1", "-i", "31", "-n", "lo", "-t", "1"], "Default G1 simulator arguments")
        require(rows["ui"]["argv"][:2] == ["--domain", "87"], "UI follows ENV ROS domain")
    finally:
        process.send_signal(signal.SIGTERM)
        finish(process, root, 143)
    process = start(root, ["--sim", "--real-checks"], full=True)
    try:
        wait_for(root, lambda rows: len(rows) == 4)
        rows = captures(root)
        require("--sim" in rows["anakin_env"]["argv"] and "--real-checks" in rows["anakin_env"]["argv"],
                "Real checks are forwarded only to the simulation ENV")
        require(rows["sim"]["argv"][:8] == ["-r", "g1", "-i", "31", "-n", "lo", "-t", "1"],
                "Real-checks simulation remains on loopback SDK domain 31")
    finally:
        process.send_signal(signal.SIGTERM)
        finish(process, root, 143)
    custom_rules = root / "real rules with spaces.yaml"
    custom_rules.write_text("mode: real\ntransport: {ros_domain: 17}\n")
    process = start(root, ["--sim", "--real-checks", "--real-config", str(custom_rules)])
    try:
        wait_for(root, lambda rows: len(rows) == 2)
        rows = captures(root)
        require(str(custom_rules) in rows["anakin_env"]["argv"] and rows["anakin_env"]["domain"] == "87",
                "Custom real checks do not replace simulation transport/domain")
    finally:
        process.send_signal(signal.SIGTERM)
        finish(process, root, 143)
    process = start(root, ["--real", "--real-checks"])
    finish(process, root, 2)
    require(not captures(root), "Real checks cannot enable hardware transport")
    process = start(root, ["--real-config", str(custom_rules)])
    finish(process, root, 2)
    require(not captures(root), "A real rules path requires explicit real checks")
    unsafe = root / "unsafe-sim.yaml"
    unsafe.write_text("mode: sim\ntransport: {ros_domain: 87, interface: eth0, sdk_domain: 31}\n")
    process = start(root, ["--real-checks", "--config", str(unsafe)])
    finish(process, root, 2)
    require(not captures(root), "Real-checks simulation rejects non-loopback transport before spawn")
    process = start(root, [])
    try:
        wait_for(root, lambda rows: len(rows) == 2)
        require(not captures(root)["anakin_env"]["tty"], "Automatic ENV runs without terminal input")
    finally:
        process.send_signal(signal.SIGTERM)
        finish(process, root, 143)
    process = start(root, ["--input", "keyboard"])
    finish(process, root, 2)
    require(not captures(root), "Removed keyboard source is rejected")
    override = root / "override with spaces.yaml"
    override.write_text("mode: sim\ntransport: {ros_domain: '89'}\n")
    process = start(root, ["--config", str(override), "--input", "remote",
                           "--mc-ros-arg=-p", "--mc-ros-arg=label:=value with spaces"])
    try:
        wait_for(root, lambda rows: len(rows) == 2)
        rows = captures(root)
        require(rows["anakin_env"]["domain"] == rows["anakin_mc"]["domain"] == "89", "Match selected YAML domain")
        require(rows["anakin_env"]["prefix"].endswith("anakin_env/install/anakin_env"), "Separate ENV prefix")
        require(rows["anakin_mc"]["prefix"].endswith("anakin_mc/install/anakin_mc"), "Separate MC prefix")
        require(str(override) in rows["anakin_env"]["argv"], "Preserve configuration path with spaces")
        require(rows["anakin_mc"]["argv"] == ["-p", "label:=value with spaces"], "Preserve ROS argument tokens")
        require(not rows["anakin_mc"]["tty"], "MC must not own terminal input")
    finally:
        process.send_signal(signal.SIGTERM)
        finish(process, root, 143)
    for signum, expected in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
        process = start(root, ["--input", "remote"])
        try:
            wait_for(root, lambda rows: len(rows) == 2)
        finally:
            process.send_signal(signum)
            finish(process, root, expected)
    for variable, code in (("TEST_ENV_EXIT", 17), ("TEST_MC_EXIT", 18)):
        process = start(root, ["--input", "remote"], {variable: str(code)})
        finish(process, root, code)
        require(len(captures(root)) == 2, "Both stubs must participate in child-exit regression")
    override.write_text("mode: sim\ntransport: {ros_domain: 87, ros_domain: 89}\n")
    process = start(root, ["--config", str(override), "--input", "remote"])
    finish(process, root, 2)
    require(not captures(root), "Reject duplicate YAML keys before spawning")
    process = start(root, ["--config", str(config / "real.yaml"), "--input", "remote"])
    finish(process, root, 2)
    require(not captures(root), "Reject mode mismatch before spawning")
    process = start(root, ["--input", "remote"], {"TEST_PREFLIGHT_FAIL": "anakin_mc"})
    finish(process, root, 2)
    require(not captures(root), "Reject invalid installation before spawning")
    process = start(root, [], {"TEST_STUBBORN": "1"})
    try:
        wait_for(root, lambda rows: len(rows) == 2 and (root / "records/anakin_env.ready").exists())
        require(not captures(root)["anakin_env"]["tty"], "Stubborn ENV has no terminal dependency")
    finally:
        process.send_signal(signal.SIGTERM)
        finish(process, root, 143)


def check_build(root):
    tools = root / "fake tools"
    tools.mkdir()
    record = root / "commands.jsonl"
    cmake = tools / "cmake"
    cmake.write_text("""#!/usr/bin/python3
import json, os, sys
with open(os.environ["TEST_COMMANDS"], "a") as out:
    out.write(json.dumps(sys.argv[1:]) + "\\n")
if "-S" in sys.argv and os.environ.get("TEST_FAIL_CONFIG"):
    sys.exit(43)
""")
    cmake.chmod(0o755)
    shutil.copy2(cmake, tools / "ctest")
    ros = root / "fake ROS"
    ros.mkdir()
    (ros / "setup.bash").write_text(":\n")
    ort = root / "anakin_mc/.deps/onnxruntime-linux-x64-1.20.1"
    (ort / "include").mkdir(parents=True)
    (ort / "lib").mkdir()
    (ort / "include/onnxruntime_cxx_api.h").touch()
    (ort / "lib/libonnxruntime.so").touch()
    (ort / "VERSION_NUMBER").write_text("1.20.1\n")
    env = environment(root)
    env.update(PATH=f"{tools}:{env['PATH']}", ROS_PREFIX=str(ros), TEST_COMMANDS=str(record))
    (root / "anakin_env/build.sh").rename(root / "anakin_env/build.saved")
    result = subprocess.run([str(root / "build.sh"), "mc", "--jobs", "3", "--test"], env=env,
                            cwd="/tmp", capture_output=True, text=True, timeout=10)
    require(result.returncode == 0, f"Fake build failed: {result.stdout} {result.stderr}")
    (root / "anakin_env/build.saved").rename(root / "anakin_env/build.sh")
    commands = [json.loads(line) for line in record.read_text().splitlines()]
    configure = [command for command in commands if "-S" in command]
    require([command[1] for command in configure] ==
            [str(root / "anakin_sdk"), str(root / "anakin_mc")], "Selective build order: SDK then MC")
    for command in configure:
        repo = Path(command[1])
        require(command[command.index("-B") + 1] == str(repo / "build" / repo.name), "Local build directory")
        require(f"-DCMAKE_INSTALL_PREFIX={repo}/install/{repo.name}" in command, "Local install prefix")
    require(any("--parallel" in command and "3" in command for command in commands), "Forward parallelism")
    record.unlink()
    env["TEST_FAIL_CONFIG"] = "1"
    result = subprocess.run([str(root / "build.sh")], env=env, cwd="/tmp",
                            capture_output=True, text=True, timeout=10)
    require(result.returncode == 43, "Propagate configure failure through log tee and parent")
    commands = [json.loads(line) for line in record.read_text().splitlines()]
    require(len(commands) == 1 and "-S" in commands[0], "Do not build/install after configure failure")
    for name in ("build", "install", "log", "logs"):
        require(not (root / name).exists(), f"No root output directory: {name}")


def main():
    with tempfile.TemporaryDirectory(prefix="AnakinC checks ") as directory:
        root = Path(directory)
        config = fixture(root)
        check_runtime(root, config)
        check_build(root)
    print("PASS: independent build order/failures, domain/args, preflight, headless input, signals, child cleanup, root layout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
