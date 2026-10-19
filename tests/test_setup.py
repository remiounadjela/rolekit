"""Automatic private workspaces and isolated optional dependency setup."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


REPO = Path(__file__).resolve().parents[1]
START = REPO / "skills/onboard-candidate/scripts/start.py"
SPEC = importlib.util.spec_from_file_location("rolekit_setup", START)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
runtime = setup.runtime


def files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "private-data"
        self.environment = mock.patch.dict(os.environ, {"ROLEKIT_DATA_DIR": str(self.data)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_start(self, *args, success=True):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = setup.main(list(map(str, args)))
        self.assertEqual(code, 0 if success else 1, output.getvalue() + error.getvalue())
        return json.loads(output.getvalue())

    def test_blank_no_name_startup_needs_no_dependency_or_initial_questionnaire(self):
        with mock.patch.object(runtime, "ensure_pdf_python") as dependencies:
            result = self.run_start()
        dependencies.assert_not_called()
        workspace = Path(result["workspace"])
        self.assertEqual(workspace.parent, (self.data / "workspaces").resolve())
        self.assertEqual(len(workspace.name), 36)
        self.assertTrue(result["needs_candidate_name"])
        self.assertEqual(result["candidate"], {"name": "New candidate"})
        self.assertEqual(result["setup_status"], "awaiting_input")
        self.assertEqual(result["inputs"], [])
        self.assertEqual(result["profile_status"], "not_assessed")
        self.assertFalse((self.data / "runtime").exists())
        if sys.platform != "win32":
            self.assertEqual(workspace.stat().st_mode & 0o077, 0)

    def test_same_name_creates_new_isolated_candidates_without_active_pointer(self):
        first = self.run_start("--name", "Alex Example")
        before = files(Path(first["workspace"]))
        second = self.run_start("--name", "Alex Example")
        self.assertNotEqual(first["workspace"], second["workspace"])
        self.assertEqual(files(Path(first["workspace"])), before)
        self.assertEqual(set(path.name for path in self.data.iterdir()), {"workspaces"})
        self.assertFalse(first["needs_candidate_name"])

    def test_explicit_resume_preserves_profile_and_appends_transcript(self):
        first = self.run_start("--name", "Alex Example")
        workspace = Path(first["workspace"])
        profile = workspace / "profile/about.md"
        profile.write_text("Existing candidate profile")
        transcript = self.root / "notes.txt"
        raw = b"I volunteered at a community event.\r\n"
        transcript.write_bytes(raw)
        with mock.patch.object(runtime, "ensure_pdf_python") as dependencies:
            resumed = self.run_start("--workspace", workspace, "--experience", transcript)
        dependencies.assert_not_called()
        self.assertEqual(resumed["workspace_status"], "resumed")
        self.assertEqual(resumed["workspace"], first["workspace"])
        self.assertEqual(profile.read_text(), "Existing candidate profile")
        self.assertEqual((Path(resumed["inputs"][0]["folder"]) / "original/notes.txt").read_bytes(), raw)
        self.assertEqual(len(list((self.data / "workspaces").iterdir())), 1)

    def test_docx_and_repeated_experience_inputs_use_only_standard_library(self):
        cv = self.root / "upload.docx"
        with zipfile.ZipFile(cv, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Community projects</w:t></w:r></w:p></w:body></w:document>')
        first, second = self.root / "first.txt", self.root / "second.md"
        first.write_text("I organized a workshop.")
        second.write_text("I also mentored students.")
        with mock.patch.object(runtime, "ensure_pdf_python") as dependencies:
            result = self.run_start("--cv", cv, "--experience", first, "--experience", second)
        dependencies.assert_not_called()
        self.assertEqual([item["input_type"] for item in result["inputs"]], ["cv", "experience", "experience"])
        self.assertTrue(all(item["original_preserved"] for item in result["inputs"]))
        self.assertTrue(all(item["extraction_status"] == "extracted" for item in result["inputs"]))
        self.assertFalse((self.data / "runtime").exists())

    def test_explicit_new_workspace_does_not_use_data_directory(self):
        path = self.root / "chosen-candidate"
        result = self.run_start("--workspace", path)
        self.assertEqual(Path(result["workspace"]), path.resolve())
        self.assertFalse(self.data.exists())

    def test_explicit_existing_workspace_identity_mismatch_is_rejected_without_mutation(self):
        first = self.run_start("--name", "Alex Example")
        workspace = Path(first["workspace"])
        before = files(workspace)
        result = self.run_start("--workspace", workspace, "--name", "Other Person", success=False)
        self.assertEqual(result["setup_status"], "failed")
        self.assertIn("differs", result["diagnostic"])
        self.assertEqual(files(workspace), before)

    def test_invalid_explicit_workspace_is_not_initialized_over(self):
        path = self.root / "not-a-workspace"
        path.mkdir()
        (path / "keep.txt").write_text("Keep")
        before = files(path)
        result = self.run_start("--workspace", path, success=False)
        self.assertEqual(result["setup_status"], "failed")
        self.assertEqual(files(path), before)

    def test_uploaded_text_from_unrelated_cwd_works_with_copied_readonly_skill_layout(self):
        install = self.root / "installed"
        shutil.copytree(REPO / "skills/tailor-cv", install / "tailor-cv")
        shutil.copytree(REPO / "skills/onboard-candidate", install / "onboard-candidate")
        before = files(install)
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        cv = self.root / "upload.md"
        cv.write_bytes(b"# Jordan Candidate\n\nProject and education history.\n")
        command = [sys.executable, "-B", str(install / "onboard-candidate/scripts/start.py"), "--cv", str(cv)]
        completed = subprocess.run(command, cwd=unrelated, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["needs_candidate_name"])
        self.assertTrue(result["inputs"][0]["original_preserved"])
        self.assertEqual(result["runtime"]["status"], "not_needed")
        self.assertEqual(files(install), before)
        self.assertEqual(list(unrelated.iterdir()), [])
        config = (Path(result["workspace"]) / "rolekit.json").read_text()
        self.assertNotIn(str(cv), config)

    def test_offline_pdf_dependency_failure_still_preserves_original_and_reports_next_action(self):
        # A small real venv without packages makes this independent of the test
        # runner's optional pypdf installation, and performs no downloads.
        bare = self.root / "bare-python"
        completed = subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bare)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        python = bare / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        cv = self.root / "offline.pdf"
        raw = b"%PDF-1.4\nUploaded bytes remain intact even while offline.\n"
        cv.write_bytes(raw)
        with mock.patch.object(runtime, "ensure_pdf_python", side_effect=runtime.RuntimeSetupError("Package network unavailable")), mock.patch.object(setup.sys, "executable", str(python)):
            result = self.run_start("--cv", cv, success=False)
        self.assertEqual(result["runtime"]["status"], "failed")
        self.assertEqual(result["setup_status"], "needs_attention")
        self.assertIn("host-provided local extraction", result["next_action"])
        imported = result["inputs"][0]
        self.assertTrue(imported["original_preserved"])
        self.assertEqual((Path(imported["folder"]) / "original/offline.pdf").read_bytes(), raw)
        metadata = json.loads((Path(imported["folder"]) / "input.json").read_text())
        self.assertEqual(metadata["extraction"]["status"], "needs_review")
        self.assertEqual(metadata["extraction"]["method"], "pdf-unavailable")

    def test_skip_dependency_option_never_invokes_package_setup(self):
        cv = self.root / "cv.pdf"
        cv.write_bytes(b"Not a usable PDF, but preservation is possible")
        with mock.patch.object(runtime, "ensure_pdf_python") as dependencies:
            result = self.run_start("--cv", cv, "--skip-dependencies", success=False)
        dependencies.assert_not_called()
        self.assertEqual(result["runtime"]["status"], "skipped")
        self.assertTrue(result["inputs"][0]["original_preserved"])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "private-data"
        patch = mock.patch.dict(os.environ, {"ROLEKIT_DATA_DIR": str(self.data)})
        patch.start()
        self.addCleanup(patch.stop)
        self.directory = self.data / "runtime" / f"{sys.version_info.major}.{sys.version_info.minor}"
        self.python = self.directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    def probe(self, versions=None, private=False):
        return {"version": list(sys.version_info[:2]), "prefix": str(self.directory if private else self.root / "host"),
                "base_prefix": str(self.root / "host"), "versions": versions or {}, "issues": {}}

    def make_runtime(self, system_site=False):
        self.python.parent.mkdir(parents=True, exist_ok=True)
        self.python.write_text("simulated Python launcher")
        (self.directory / "pyvenv.cfg").write_text(f"include-system-site-packages = {'true' if system_site else 'false'}\n")

    def test_platform_data_defaults_and_explicit_override(self):
        self.assertEqual(runtime.data_dir(), self.data)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(Path, "home", return_value=self.root):
            with mock.patch.object(runtime.sys, "platform", "darwin"):
                self.assertEqual(runtime.data_dir(), self.root / "Library/Application Support/RoleKit")
            with mock.patch.object(runtime.sys, "platform", "linux"):
                self.assertEqual(runtime.data_dir(), self.root / ".local/share/rolekit")
                with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "xdg")}):
                    self.assertEqual(runtime.data_dir(), self.root / "xdg/rolekit")
            with mock.patch.object(runtime.sys, "platform", "win32"), mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "local")}):
                self.assertEqual(runtime.data_dir(), self.root / "local/RoleKit")
        with mock.patch.dict(os.environ, {"ROLEKIT_DATA_DIR": "relative-directory"}):
            with self.assertRaisesRegex(runtime.RuntimeSetupError, "absolute"):
                runtime.data_dir()

    def test_existing_host_dependency_needs_no_install_or_data_directory(self):
        with mock.patch.object(runtime, "_probe", return_value=self.probe({"pypdf": "6.20.1"})), mock.patch.object(runtime, "_run") as runner:
            python = runtime.ensure_pdf_python()
        self.assertEqual(python, Path(sys.executable).absolute())
        runner.assert_not_called()
        self.assertFalse(self.data.exists())

    def test_private_runtime_is_reused_and_grows_without_resetting_or_global_installs(self):
        installed, commands = {}, []

        def probe(python, required):
            private = python == self.python
            versions = {name: installed.get(name) if private else None for name in required}
            return self.probe(versions, private)

        def run(command, purpose):
            commands.append(command)
            if "venv" in command:
                self.make_runtime()
                (self.directory / "keep.txt").write_text("Retain runtime state")
            elif "pip" in command:
                self.assertEqual(command[0], str(self.python))
                self.assertIn("--isolated", command)
                self.assertNotIn("--user", command)
                for argument in command:
                    if "==" in argument:
                        name, version = argument.split("==")
                        installed[name] = version
            else:
                self.fail(f"Unexpected package setup command: {command}")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(runtime, "_probe", side_effect=probe), mock.patch.object(runtime, "_run", side_effect=run), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runtime.ensure_pdf_python(), self.python)
            self.assertEqual(runtime.ensure_packages([runtime.PDF_REQUIREMENT, "playwright==1.63.0"]), self.python)
            self.assertEqual(runtime.ensure_packages([runtime.PDF_REQUIREMENT, "playwright==1.63.0"]), self.python)
        self.assertEqual(sum("venv" in command for command in commands), 1)
        pip_commands = [command for command in commands if "pip" in command]
        self.assertEqual(len(pip_commands), 2)
        self.assertIn("pypdf==6.20.1", pip_commands[0])
        self.assertNotIn("pypdf==6.20.1", pip_commands[1])
        self.assertIn("playwright==1.63.0", pip_commands[1])
        self.assertFalse(any(Path(command[0]).name in {"uv", "uv.exe"} for command in commands))
        self.assertEqual((self.directory / "keep.txt").read_text(), "Retain runtime state")

    def test_existing_system_site_runtime_is_rejected_without_installing(self):
        self.make_runtime(system_site=True)
        with mock.patch.object(runtime, "_probe", return_value=self.probe()), mock.patch.object(runtime, "_run") as runner:
            with self.assertRaisesRegex(runtime.RuntimeSetupError, "system site"):
                runtime.ensure_pdf_python()
        runner.assert_not_called()

    def test_wrong_runtime_identity_is_rejected_before_pip(self):
        self.make_runtime()
        with mock.patch.object(runtime, "_probe", return_value=self.probe()), mock.patch.object(runtime, "_run") as runner:
            with self.assertRaisesRegex(runtime.RuntimeSetupError, "isolated virtual"):
                runtime.ensure_pdf_python()
        runner.assert_not_called()

    def test_dependency_pin_validation_and_python_version_validation(self):
        for requirements in (["pypdf"], ["pypdf>=6"], ["pypdf==6.20.1", "pypdf==1.0"]):
            with self.subTest(requirements=requirements):
                with self.assertRaises(runtime.RuntimeSetupError):
                    runtime.ensure_packages(requirements)
        bad = self.probe({"pypdf": "6.20.1"})
        bad["version"] = [0, 0]
        with mock.patch.object(runtime, "_run", return_value=subprocess.CompletedProcess([], 0, json.dumps(bad), "")):
            with self.assertRaisesRegex(runtime.RuntimeSetupError, "version differs"):
                runtime._probe(Path(sys.executable), {"pypdf": "6.20.1"})

    def test_private_install_failure_is_actionable_and_does_not_fall_back_to_global_pip(self):
        self.make_runtime()
        with mock.patch.object(runtime, "_probe", side_effect=[self.probe(), self.probe(private=True)]), mock.patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "offline")) as runner, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(runtime.RuntimeSetupError, "No global packages were installed"):
                runtime.ensure_pdf_python()
        self.assertEqual(runner.call_count, 1)
        command = runner.call_args.args[0]
        self.assertEqual(command[0], str(self.python))
        self.assertIn("pip", command)
        self.assertIn("pypdf==6.20.1", command)


if __name__ == "__main__":
    unittest.main()
