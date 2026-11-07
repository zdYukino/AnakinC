"""Exercise SDK bootstrap and prefix selection without modifying system dependencies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parents[1]


def run(root, env, *args, expected=0):
    result = subprocess.run([str(root / "boostup.sh"), *args], cwd="/tmp", env=env,
                            text=True, capture_output=True, timeout=20)
    assert result.returncode == expected, result.stdout + result.stderr
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="unitree setup ") as temp:
        root = Path(temp)
        (root / "scripts").mkdir()
        (root / "bin").mkdir()
        (root / "anakin_mc/scripts").mkdir(parents=True)
        for name in ("boostup.sh", "build.sh", "em_run.sh"):
            shutil.copy2(SOURCE / name, root / name)
        helper = (SOURCE / "scripts/unitree_sdk2.sh").read_text().replace('/usr/local', str(root / 'system'))
        (root / "scripts/unitree_sdk2.sh").write_text(helper)
        # Isolate all system prefix checks in this fixture.
        boost = root / "boostup.sh"
        boost.write_text(boost.read_text().replace('/usr/local', str(root / 'system')))
        boost.chmod(0o755)
        log = root / "calls.jsonl"
        fake = '''#!/usr/bin/python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
with open(os.environ["TEST_LOG"], "a") as f:
    f.write(json.dumps([name, sys.argv[1:], os.environ.get("UNITREE_SDK2_PREFIX")]) + "\\n")
if name == "git" and "clone" in sys.argv:
    dest = pathlib.Path(sys.argv[-1]); dest.mkdir(exist_ok=True)
    (dest / "CMakeLists.txt").touch()
if name == "cmake" and "--install" in sys.argv:
    config = pathlib.Path(os.environ["TEST_ROOT"]) / "thirdparty/unitree_sdk2-install/lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake"
    config.parent.mkdir(parents=True, exist_ok=True); config.touch()
'''
        for name in ("git", "cmake", "fake-python"):
            tool = root / "bin" / name
            tool.write_text(fake)
            tool.chmod(0o755)
        env = os.environ.copy()
        env.pop("UNITREE_SDK2_PREFIX", None)
        env.update(PATH=f"{root / 'bin'}:{env['PATH']}", ANAKIN_PYTHON=str(root / "bin/fake-python"),
                   TEST_LOG=str(log), TEST_ROOT=str(root))
        run(root, env)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert sum(name == "git" and "clone" in args for name, args, _ in calls) == 1
        assert sum(name == "cmake" for name, _, _ in calls) == 3
        assert all(prefix == str(root / "thirdparty/unitree_sdk2-install") for name, _, prefix in calls if name == "fake-python")
        log.unlink()
        run(root, env)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert not any(name == "cmake" or (name == "git" and "clone" in args) for name, args, _ in calls)
        assert all(prefix == str(root / "thirdparty/unitree_sdk2-install") for name, _, prefix in calls if name == "fake-python")
        log.unlink()
        custom = str(root / "custom")
        run(root, dict(env, UNITREE_SDK2_PREFIX=custom))
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert not any(name == "cmake" or (name == "git" and "clone" in args) for name, args, _ in calls)
        assert all(prefix == custom for name, _, prefix in calls if name == "fake-python")
        system = root / "system/lib/cmake/unitree_sdk2/unitree_sdk2Config.cmake"
        system.parent.mkdir(parents=True)
        system.touch()
        log.unlink()
        run(root, env)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert all(prefix is None for name, _, prefix in calls if name == "fake-python")
        assert not any(name == "cmake" or (name == "git" and "clone" in args) for name, args, _ in calls)
    print("PASS: Unitree bootstrap, reuse, explicit prefix and system precedence")


if __name__ == "__main__":
    main()
