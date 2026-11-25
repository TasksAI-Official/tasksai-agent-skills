"""Install an isolated built or published package and exercise real, unpaid MCP calls."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def run(arguments, *, directory, environment):
    result = subprocess.run([str(a) for a in arguments], cwd=directory, env=environment,
                            capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f"Installation verification failed: {result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wheel", type=Path)
    source.add_argument("--package", help="Published PyPI name==version")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = str(args.wheel.resolve()) if args.wheel else args.package
    with tempfile.TemporaryDirectory(prefix="tasksai-public-install-") as temporary:
        root = Path(temporary)
        python = root / "isolated" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        venv.EnvBuilder(with_pip=True).create(root / "isolated")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment["PYTHONNOUSERSITE"] = "1"
        run([python, "-m", "pip", "install", "--disable-pip-version-check", target], directory=root, environment=environment)
        run([python, "-m", "pip", "check"], directory=root, environment=environment)
        config = root / "existing agent" / "config.toml"
        config.parent.mkdir()
        config.write_text('model = "preserved"\n[mcp_servers.human]\nurl = "https://example.invalid/human"\n')
        state = root / "private purchase state"
        setup = [python, "-m", "realtortasksai_connector", "setup", "--client", "codex", "--product", "all",
                 "--config-file", config, "--state-dir", state]
        run(setup, directory=root, environment=environment)
        before = config.read_bytes()
        run(setup, directory=root, environment=environment)
        assert config.read_bytes() == before
        # Probe is outside the project source tree, so only installed code is importable.
        probe = root / "probe.py"
        probe.write_text((ROOT / "scripts/mcp_probe.py").read_text())
        output = run([python, probe, config], directory=root, environment=environment)
        report = json.loads(output)
        report.update(fresh_install=True, configuration_preserved=True, setup_retry_idempotent=True,
                      platform=sys.platform, python=sys.version.split()[0], source=Path(target).name)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
