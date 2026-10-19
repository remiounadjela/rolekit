"""Automatic PDF-tool setup preserves renderer behavior and stays private."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "skills/tailor-cv/scripts/render_auto.py"
SPEC = importlib.util.spec_from_file_location("rolekit_render_setup", SCRIPT)
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


class SetupError(Exception):
    pass


class RenderSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / "draft"
        self.folder.mkdir()
        (self.folder / "cv.html").write_text("<html><body>Candidate CV</body></html>")
        self.style = self.root / "style.css"
        self.style.write_text("body { color: black; }")
        self.runtime = SimpleNamespace(
            RuntimeSetupError=SetupError, PDF_REQUIREMENT="pypdf==6.20.1",
            data_dir=mock.Mock(return_value=self.root / "private-data"),
            ensure_pdf_python=mock.Mock(return_value=Path("/managed/python")),
            ensure_packages=mock.Mock(return_value=Path("/managed/python")),
        )

    def test_native_browser_needs_no_browser_download(self):
        with mock.patch.object(render, "sibling", return_value=SimpleNamespace(browser_path=lambda: "/native/chrome")):
            python, environment = render.prepare_browser(self.runtime, Path("/managed/python"), {})
        self.assertEqual(python, Path("/managed/python"))
        self.assertEqual(environment["ROLEKIT_CHROME"], "/native/chrome")
        self.runtime.ensure_packages.assert_not_called()

    def test_invalid_explicit_browser_override_does_not_silently_install(self):
        with mock.patch.object(render, "sibling", return_value=SimpleNamespace(browser_path=lambda: None)):
            with self.assertRaises(SetupError):
                render.prepare_browser(self.runtime, Path("/managed/python"), {"CHROME_BIN": "/wrong"})
        self.runtime.ensure_packages.assert_not_called()

    def test_missing_browser_installs_only_private_chromium(self):
        browser = self.root / "managed-chrome"
        with mock.patch.object(render, "sibling", return_value=SimpleNamespace(browser_path=lambda: None)), \
             mock.patch.object(render, "chromium_path", side_effect=[None, browser]), \
             mock.patch.object(render.subprocess, "run") as run, contextlib.redirect_stderr(io.StringIO()):
            python, environment = render.prepare_browser(self.runtime, Path("/old/python"), {})
        self.assertEqual(python, Path("/managed/python"))
        self.runtime.ensure_packages.assert_called_once_with(["pypdf==6.20.1", "playwright==1.63.0"])
        self.assertEqual(environment["ROLEKIT_CHROME"], str(browser))
        self.assertEqual(Path(environment["PLAYWRIGHT_BROWSERS_PATH"]), self.root / "private-data/browsers/1.63.0")
        self.assertEqual(run.call_args.args[0], ["/managed/python", "-I", "-B", "-m", "playwright", "install", "--only-shell", "chromium"])
        self.assertNotIn("--with-deps", run.call_args.args[0])

    def test_repeated_export_reuses_managed_browser(self):
        with mock.patch.object(render, "sibling", return_value=SimpleNamespace(browser_path=lambda: None)), \
             mock.patch.object(render, "chromium_path", return_value=self.root / "already-installed"), \
             mock.patch.object(render.subprocess, "run") as run:
            render.prepare_browser(self.runtime, Path("/managed/python"), {})
        run.assert_not_called()

    def test_managed_browser_discovery_uses_executable_shell_in_owned_cache(self):
        cache = self.root / "browsers"
        shell = cache / "chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"
        shell.parent.mkdir(parents=True)
        shell.write_text("synthetic executable")
        shell.chmod(0o700)
        other = cache / "chromium-1243/chrome"
        other.parent.mkdir()
        other.write_text("full browser is not the shell")
        other.chmod(0o700)
        self.assertEqual(render.chromium_path({"PLAYWRIGHT_BROWSERS_PATH": str(cache)}), shell)

    def test_browser_installer_cannot_execute_module_from_callers_directory(self):
        bare = self.root / "bare-python"
        subprocess.run([sys.executable, "-I", "-B", "-m", "venv", "--without-pip", str(bare)], check=True, capture_output=True)
        python = bare / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        self.runtime.ensure_packages.return_value = python
        marker = self.root / "executed-local-module"
        (self.root / "playwright.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
        old_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with mock.patch.object(render, "sibling", return_value=SimpleNamespace(browser_path=lambda: None)), \
                 tempfile.TemporaryFile(mode="w+") as log, contextlib.redirect_stderr(log):
                with self.assertRaises(SetupError):
                    render.prepare_browser(self.runtime, python, dict(os.environ))
        finally:
            os.chdir(old_cwd)
        self.assertFalse(marker.exists())

    def test_failed_browser_download_keeps_existing_cv_artifacts(self):
        (self.folder / "cv.pdf").write_bytes(b"existing PDF")
        (self.folder / "render.json").write_text(json.dumps({"status": "verified"}))
        before = {item.name: item.read_bytes() for item in self.folder.iterdir()}
        with mock.patch.object(render, "sibling", return_value=self.runtime), \
             mock.patch.object(render, "prepare_browser", side_effect=SetupError("offline")), \
             contextlib.redirect_stderr(io.StringIO()):
            code = render.main([str(self.folder), "--style", str(self.style)])
        self.assertEqual(code, 1)
        after = {item.name: item.read_bytes() for item in self.folder.iterdir()}
        self.assertEqual({key: value for key, value in before.items() if key != "render.json"},
                         {key: value for key, value in after.items() if key != "render.json"})
        report = json.loads(after["render.json"])
        self.assertEqual(report["status"], "failed")
        self.assertIn("offline", report["error"])

    def test_export_forwards_exact_folder_style_timeout_and_result(self):
        with mock.patch.object(render, "sibling", return_value=self.runtime), \
             mock.patch.object(render, "prepare_browser", return_value=(Path("/managed/python"), {"ROLEKIT_CHROME": "/native/chrome"})), \
             mock.patch.object(render.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as run:
            code = render.main([str(self.folder), "--style", str(self.style), "--timeout", "12"])
        self.assertEqual(code, 1)
        self.assertEqual(run.call_args.args[0], ["/managed/python", "-I", "-B", str(render.HERE / "render.py"), str(self.folder.resolve()), "--style", str(self.style.resolve()), "--timeout", "12.0"])

    def test_missing_cv_does_not_trigger_downloads(self):
        with mock.patch.object(render, "sibling") as sibling, contextlib.redirect_stderr(io.StringIO()):
            code = render.main([str(self.root / "missing"), "--style", str(self.style)])
        self.assertEqual(code, 1)
        sibling.assert_not_called()


if __name__ == "__main__":
    unittest.main()
