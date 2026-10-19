#!/usr/bin/env python3
"""Set up private PDF tools as needed, then run the verified local renderer."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PLAYWRIGHT = "playwright==1.63.0"


def sibling(name):
    spec = importlib.util.spec_from_file_location(f"rolekit_render_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chromium_path(environment: dict) -> Path | None:
    # The public Playwright executable_path describes full Chromium, even for a
    # shell-only install. Discover the shell only inside our version-scoped cache.
    root = Path(environment["PLAYWRIGHT_BROWSERS_PATH"])
    names = {"chrome-headless-shell", "headless_shell", "chrome-headless-shell.exe", "headless_shell.exe"}
    for directory in sorted(root.glob("chromium_headless_shell-*")):
        for path in sorted(directory.rglob("*")):
            if path.name in names and path.is_file() and os.access(path, os.X_OK):
                return path
    return None


def prepare_browser(runtime, python: Path, environment: dict) -> tuple[Path, dict]:
    """Prefer existing Chrome; install a private browser only when none is available."""
    rolekit = sibling("rolekit")
    browser = rolekit.browser_path()
    if browser:
        environment["ROLEKIT_CHROME"] = browser
        return python, environment
    if any(environment.get(key) for key in ("ROLEKIT_CHROME", "CHROME_BIN")):
        raise runtime.RuntimeSetupError("The configured Chrome path is unavailable. Correct the explicit browser setting before PDF export.")
    python = runtime.ensure_packages([runtime.PDF_REQUIREMENT, PLAYWRIGHT])
    # This browser belongs to RoleKit, separate from personal browser profiles.
    environment["PLAYWRIGHT_BROWSERS_PATH"] = str(runtime.data_dir() / "browsers" / PLAYWRIGHT.split("==")[1])
    environment["PLAYWRIGHT_SKIP_BROWSER_GC"] = "1"
    browser = chromium_path(environment)
    if browser is None:
        print("RoleKit: downloading a private Chromium for PDF export…", file=sys.stderr)
        try:
            subprocess.run(
                [str(python), "-I", "-B", "-m", "playwright", "install", "--only-shell", "chromium"],
                env=environment, stdout=sys.stderr, stderr=sys.stderr, check=True, timeout=600,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise runtime.RuntimeSetupError("Private Chromium setup failed. CV inputs and profile remain available; check network or host restrictions before retrying PDF export.") from exc
        browser = chromium_path(environment)
    if browser is None:
        raise runtime.RuntimeSetupError("Chromium setup did not produce an executable. Continue profile work and report PDF export as blocked.")
    environment["ROLEKIT_CHROME"] = str(browser)
    return python, environment


def setup_report(folder: Path, started: str, error: str | None = None) -> None:
    """Invalidate an earlier verified report before setup as the renderer does."""
    if not folder.is_dir():
        return
    report = {"schema_version": 1, "status": "failed" if error else "in_progress", "started_at": started}
    if error:
        report.update({"failed_at": datetime.now(timezone.utc).isoformat(), "error": error, "attempts": []})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, prefix=".render-setup-", suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, folder / "render.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application_folder", type=Path)
    parser.add_argument("--style", type=Path)
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args(argv)
    folder = args.application_folder.expanduser().resolve()
    style = args.style.expanduser().resolve() if args.style else HERE.parent / "assets/style.css"
    started = datetime.now(timezone.utc).isoformat()
    try:
        setup_report(folder, started)
    except OSError as exc:
        print(f"RoleKit: Cannot record PDF verification status: {exc}", file=sys.stderr)
        return 1
    if not (folder / "cv.html").is_file() or not style.is_file():
        error = "PDF export requires an existing cv.html and stylesheet; no tools were installed."
        setup_report(folder, started, error)
        print(f"RoleKit: {error}", file=sys.stderr)
        return 1
    runtime = sibling("runtime")
    try:
        python = runtime.ensure_pdf_python()
        python, environment = prepare_browser(runtime, python, dict(os.environ))
        command = [str(python), "-I", "-B", str(HERE / "render.py"), str(folder), "--style", str(style), "--timeout", str(args.timeout)]
        code = subprocess.run(command, env=environment, check=False).returncode
        if code:
            try:
                report = json.loads((folder / "render.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = {}
            if report.get("status") != "failed":
                setup_report(folder, started, f"Renderer exited with code {code} before verification.")
        return code
    except (runtime.RuntimeSetupError, OSError, subprocess.SubprocessError) as exc:
        try:
            setup_report(folder, started, str(exc))
        except OSError:
            pass
        print(f"RoleKit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
