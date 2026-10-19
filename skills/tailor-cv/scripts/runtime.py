#!/usr/bin/env python3
"""Optional local Python packages, isolated from the host's package installation."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import sys


PDF_REQUIREMENT = "pypdf==6.20.1"


class RuntimeSetupError(ValueError):
    """The private runtime could not be prepared; host tools remain usable."""


def data_dir() -> Path:
    """Return an absolute per-user data home without creating directories."""
    override = os.environ.get("ROLEKIT_DATA_DIR")
    if override:
        directory = Path(override).expanduser()
    elif sys.platform == "darwin":
        directory = Path.home() / "Library/Application Support/RoleKit"
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        directory = (Path(local) if local else Path.home() / "AppData/Local") / "RoleKit"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        directory = (Path(xdg).expanduser() if xdg else Path.home() / ".local/share") / "rolekit"
    if not directory.is_absolute():
        raise RuntimeSetupError("ROLEKIT_DATA_DIR and platform data-directory overrides must be absolute paths")
    return directory


@contextmanager
def _private_creation():
    previous = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous)


def _run(command: list[str], purpose: str):
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeSetupError(f"{purpose} failed: {exc}. Use host-provided local extraction/rendering, or retry when local Python/package access is available.") from exc
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "No diagnostic output")[-2500:].strip()
        raise RuntimeSetupError(f"{purpose} failed: {details}. No global packages were installed. Use host-provided local tools or retry later.")
    return completed


PROBE = """
import importlib, importlib.metadata, json, sys
requirements = json.loads(sys.argv[1])
versions, issues = {}, {}
for name, expected in requirements.items():
    try:
        versions[name] = importlib.metadata.version(name)
        if versions[name] == expected and name in {'pypdf', 'playwright'}:
            importlib.import_module('playwright.sync_api' if name == 'playwright' else name)
    except Exception as exc:
        versions[name] = None
        issues[name] = str(exc)
print(json.dumps({'version': list(sys.version_info[:2]), 'prefix': sys.prefix,
                  'base_prefix': sys.base_prefix, 'versions': versions, 'issues': issues}))
"""


def _probe(python: Path, requirements: dict[str, str]) -> dict:
    completed = _run([str(python), "-I", "-B", "-c", PROBE, json.dumps(requirements)], "Python dependency validation")
    try:
        probe = json.loads(completed.stdout)
        if not isinstance(probe, dict) or not isinstance(probe.get("versions"), dict):
            raise ValueError("unexpected validation result")
        if probe.get("version") != list(sys.version_info[:2]):
            raise ValueError("interpreter version differs from the running Python")
        return probe
    except (ValueError, TypeError) as exc:
        raise RuntimeSetupError(f"Cannot validate Python runtime {python}: {exc}") from exc


def _requirements(requirements: list[str]) -> dict[str, str]:
    pinned = {}
    for requirement in requirements:
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)", requirement)
        if not match:
            raise RuntimeSetupError("Private runtime packages must use exact package==version pins")
        name, version = match.groups()
        name = re.sub(r"[-_.]+", "-", name).lower()
        if name in pinned and pinned[name] != version:
            raise RuntimeSetupError(f"Conflicting package versions requested for {name}")
        pinned[name] = version
    return pinned


def _matches(probe: dict, requirements: dict[str, str]) -> bool:
    return all(probe["versions"].get(name) == version for name, version in requirements.items())


def _validate_private(probe: dict, directory: Path) -> None:
    try:
        prefix = Path(probe["prefix"]).resolve()
        base_prefix = Path(probe["base_prefix"]).resolve()
    except (KeyError, TypeError, OSError, RuntimeError) as exc:
        raise RuntimeSetupError(f"Cannot validate private runtime identity at {directory}: {exc}") from exc
    if prefix != directory.resolve() or prefix == base_prefix:
        raise RuntimeSetupError(f"Refusing package installation: {directory} does not identify an isolated virtual environment")


def _ensure_packages(requirements: list[str]) -> Path:
    pinned = _requirements(requirements)
    current = Path(sys.executable).absolute()
    if not pinned or _matches(_probe(current, pinned), pinned):
        return current

    directory = data_dir() / "runtime" / f"{sys.version_info.major}.{sys.version_info.minor}"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise RuntimeSetupError(f"Private runtime path must be a real directory: {directory}")
    python = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not directory.exists():
        print(f"RoleKit: Preparing private Python runtime at {directory}", file=sys.stderr)
        with _private_creation():
            directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            _run([str(current), "-I", "-B", "-m", "venv", str(directory)], "Private Python environment creation")
    config = directory / "pyvenv.cfg"
    try:
        settings = {key.strip().lower(): value.strip().lower()
                    for key, value in (line.split("=", 1) for line in config.read_text(encoding="utf-8").splitlines() if "=" in line)}
    except (OSError, UnicodeError) as exc:
        raise RuntimeSetupError(f"Existing private runtime is incomplete at {directory}: {exc}. Choose another ROLEKIT_DATA_DIR or repair that private runtime.") from exc
    if settings.get("include-system-site-packages") != "false":
        raise RuntimeSetupError(f"Refusing package installation: {directory} exposes system site packages")
    probe = _probe(python, pinned)
    _validate_private(probe, directory)
    if _matches(probe, pinned):
        return python
    missing = [f"{name}=={version}" for name, version in pinned.items() if probe["versions"].get(name) != version]
    print("RoleKit: Installing optional packages in the private runtime: " + ", ".join(missing), file=sys.stderr)
    installed = _run([str(python), "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
                      "install", "--no-input", "--timeout", "15", "--retries", "0", *missing],
                     "Private dependency installation")
    if installed.stdout.strip():
        print(installed.stdout.strip(), file=sys.stderr)
    probe = _probe(python, pinned)
    _validate_private(probe, directory)
    if not _matches(probe, pinned):
        raise RuntimeSetupError("Private dependency installation completed but the requested package versions/imports could not be validated")
    return python


def ensure_packages(requirements: list[str]) -> Path:
    """Return an interpreter with exact pins, adding packages only to a private venv."""
    try:
        return _ensure_packages(requirements)
    except OSError as exc:
        raise RuntimeSetupError(f"Cannot prepare the private dependency runtime: {exc}. Use available host-provided local tools or choose a writable ROLEKIT_DATA_DIR.") from exc


def ensure_pdf_python() -> Path:
    """Return Python with the pinned local PDF reader available."""
    return ensure_packages([PDF_REQUIREMENT])
