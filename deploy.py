#!/usr/bin/env python3
"""Install MiniChat's dependencies and start the server, with uv or with plain venv + pip.

    python3 deploy.py                # uv if it is installed, otherwise venv + pip
    python3 deploy.py --mode pip     # force venv + pip (uses requirements.txt)
    python3 deploy.py --no-start     # install and run the tests, but don't start the server

Only the standard library is used, so any Python 3.8+ can run this file; the app itself needs 3.14+.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MIN_PYTHON = (3, 14)  # keep in sync with requires-python in pyproject.toml
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


class DeployError(Exception):
    pass


def step(message: str) -> None:
    print(f"\n\033[1;36m==> {message}\033[0m" if COLOR else f"\n==> {message}", flush=True)


def run(command: list[str]) -> int:
    print(f"    $ {' '.join(command).replace(str(ROOT) + os.sep, '')}", flush=True)
    try:
        return subprocess.run(command, cwd=ROOT).returncode
    except KeyboardInterrupt:
        return 130


def run_or_fail(command: list[str], what: str) -> None:
    if run(command) != 0:
        raise DeployError(f"{what} failed (see the output above)")


def succeeds(command: list[str]) -> bool:
    try:
        return subprocess.run(command, cwd=ROOT, capture_output=True).returncode == 0
    except OSError:
        return False


def has_module(python: list[str], module: str) -> bool:
    return succeeds([*python, "-c", f"import {module}"])


def python_version(python: list[str]) -> tuple[int, ...] | None:
    try:
        result = subprocess.run(
            [*python, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return tuple(int(part) for part in result.stdout.strip().split("."))


def version_text(version: tuple[int, ...]) -> str:
    return ".".join(map(str, version))


def find_python() -> list[str]:
    candidates = [[sys.executable], ["python3.14"], ["python3"], ["python"]]
    if os.name == "nt":
        candidates.append(["py", "-3"])
    for python in candidates:
        version = python_version(python)
        if version is not None and version >= MIN_PYTHON:
            print(f"    using Python {version_text(version)} ({' '.join(python)})")
            return python
    raise DeployError(
        f"Python {version_text(MIN_PYTHON)}+ was not found. Install it, or install uv "
        "(which downloads the right Python by itself): https://docs.astral.sh/uv/"
    )


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install_with_uv(uv: str) -> list[str]:
    step("Installing dependencies with uv (exact versions from uv.lock)")
    run_or_fail([uv, "sync", "--locked"], "uv sync")
    return [uv, "run", "--locked", "python"]


def install_with_pip() -> list[str]:
    step("Preparing the virtual environment (.venv)")
    base = find_python()
    if not VENV.exists():
        # Debian/Ubuntu ship Python without ensurepip unless python3.X-venv is installed
        options = [] if has_module(base, "ensurepip") else ["--without-pip"]
        run_or_fail([*base, "-m", "venv", *options, VENV.name], "creating .venv")

    python = str(venv_python())
    version = python_version([python])
    if version is None or version < MIN_PYTHON:
        found = "is broken" if version is None else f"uses Python {version_text(version)}"
        raise DeployError(f".venv {found}; delete the .venv folder and run deploy.py again")

    step("Installing dependencies with pip (requirements.txt)")
    pip = pip_command(base, python)
    run_or_fail([*pip, "install", "--disable-pip-version-check", "-r", REQUIREMENTS.name], "pip install")
    return [python]


def pip_command(base: list[str], python: str) -> list[str]:
    if has_module([python], "pip"):
        return [python, "-m", "pip"]
    if has_module([python], "ensurepip"):
        run_or_fail([python, "-m", "ensurepip", "--upgrade"], "installing pip into .venv")
        return [python, "-m", "pip"]
    if has_module(base, "pip"):
        # no pip inside .venv (e.g. created by uv or without ensurepip): drive it with the system pip
        return [*base, "-m", "pip", "--python", python]
    raise DeployError(
        "pip is not available. On Debian/Ubuntu: sudo apt install python3.14-venv "
        "(or python3-pip), then run deploy.py again"
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install MiniChat's dependencies and start the server.")
    parser.add_argument(
        "--mode", choices=["auto", "uv", "pip"], default="auto",
        help="auto (default): uv if it is on PATH, otherwise venv + pip",
    )
    parser.add_argument("--no-start", action="store_true", help="install and run the tests, then stop")
    parser.add_argument("--skip-tests", action="store_true", help="start the server without running the tests")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    uv = shutil.which("uv")
    try:
        if args.mode == "uv" and uv is None:
            raise DeployError("uv was not found on PATH; install it (https://docs.astral.sh/uv/) or use --mode pip")
        python = install_with_uv(uv) if args.mode != "pip" and uv else install_with_pip()
    except DeployError as error:
        print(f"\nerror: {error}", file=sys.stderr)
        return 1

    if args.no_start:
        if args.skip_tests:
            return 0
        step("Running the tests")
        return run([*python, "-m", "tests"])

    step("Starting MiniChat on port 5000 (Ctrl+C to stop)")
    return run([*python, "run.py", *(["--skip-tests"] if args.skip_tests else [])])


if __name__ == "__main__":
    sys.exit(main())
