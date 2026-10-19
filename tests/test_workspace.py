"""Workspace isolation, no-clobber behavior, and path containment checks."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "skills/tailor-cv/scripts/rolekit.py"
SPEC = importlib.util.spec_from_file_location("rolekit_workspace", MODULE_PATH)
rolekit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rolekit)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "packaged-assets"
        self.assets.mkdir()
        for name in rolekit.PROFILE_FILES:
            (self.assets / name).write_text(f"Neutral asset: {name}\n", encoding="utf-8")
        original = rolekit.PROFILE_ASSETS
        rolekit.PROFILE_ASSETS = self.assets
        self.addCleanup(setattr, rolekit, "PROFILE_ASSETS", original)

    def run_cli(self, *args, success=True):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = rolekit.main(list(map(str, args)))
        self.assertEqual(code, 0 if success else 1, (output.getvalue(), error.getvalue()))
        return output.getvalue(), error.getvalue()

    def init(self, directory="alice", name="Alice Example"):
        path = self.root / directory
        self.run_cli("init", path, "--name", name)
        return path

    def config(self, path):
        return json.loads((path / "rolekit.json").read_text())

    def test_init_manifest_is_neutral_and_sources_empty(self):
        path = self.init()
        config = self.config(path)
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["candidate"], {"name": "Alice Example"})
        self.assertEqual(config["defaults"]["page_limit"], 1)
        self.assertEqual(json.loads((path / config["sources"]).read_text()), [])
        self.assertEqual((path / "profile/master_cv.html").read_bytes(), (self.assets / "master_cv.html").read_bytes())
        self.run_cli("doctor", path)

    def test_two_profiles_are_isolated(self):
        alice = self.init()
        bob = self.init("bob", "Bob Example")
        jd = self.root / "posting.md"
        original = b"# Engineer\r\n\r\nAll duties.\r\n\xe2\x80\xa2 No summaries.\r\n"
        jd.write_bytes(original)
        self.run_cli("new", alice, "Acme", "Engineer", "--jd", jd, "--url", "https://example.com/jobs/1")
        self.assertEqual(list((bob / "applications").iterdir()), [])
        folder = next((alice / "applications").iterdir())
        self.assertEqual((folder / "jd.md").read_bytes(), original)
        data = json.loads((folder / "application.json").read_text())
        self.assertEqual(data["candidate"]["name"], "Alice Example")
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["submission"]["status"], "not_started")
        self.assertIsNone(data["submission"]["submitted_at"])
        self.assertFalse((folder / "cv.html").exists())
        self.run_cli("doctor", alice)
        self.run_cli("doctor", bob)

    def test_new_profile_has_separate_library_style_and_review_files(self):
        path = self.init()
        config = self.config(path)
        for key in ("experiences", "cv_style", "review"):
            target = path / config["profile"][key]
            self.assertTrue(target.is_file())
            self.assertNotEqual(target, path / config["profile"]["master_cv"])
        self.assertEqual(json.loads((path / config["sources"]).read_text()), [])

    def test_legacy_workspace_without_onboarding_keys_still_validates(self):
        path = self.init()
        config = self.config(path)
        for key in ("experiences", "cv_style", "review"):
            del config["profile"][key]
        (path / "rolekit.json").write_text(json.dumps(config))
        self.run_cli("doctor", path)
        self.run_cli("inspect", path, "--json")

    def test_optional_profile_paths_support_custom_locations_and_reject_escape(self):
        path = self.init()
        config = self.config(path)
        library = path / "profile/custom-history.md"
        library.write_text("Candidate-provided project history")
        config["profile"]["experiences"] = "profile/custom-history.md"
        (path / "rolekit.json").write_text(json.dumps(config))
        self.run_cli("doctor", path)
        library.unlink()
        library.symlink_to(self.assets / "experiences.md")
        self.run_cli("doctor", path, success=False)
        self.run_cli("new", path, "Acme", "Engineer", success=False)
        self.assertEqual(list((path / "applications").iterdir()), [])

    def test_init_never_clobbers_existing_workspace_or_directory(self):
        path = self.init()
        before = (path / "rolekit.json").read_bytes()
        self.run_cli("init", path, "--name", "Changed", success=False)
        self.assertEqual((path / "rolekit.json").read_bytes(), before)
        empty = self.root / "empty"
        empty.mkdir()
        self.run_cli("init", empty, "--name", "Changed", success=False)
        self.assertEqual(list(empty.iterdir()), [])

    def test_collision_adds_suffix_and_preserves_existing_files(self):
        path = self.init()
        self.run_cli("new", path, "Acme, Inc.", "AI Lead")
        first = path / "applications/acme-inc_ai-lead"
        original = (first / "application.json").read_bytes()
        self.run_cli("new", path, "Acme, Inc.", "AI Lead")
        self.assertTrue((path / "applications/acme-inc_ai-lead_2/application.json").exists())
        self.assertEqual((first / "application.json").read_bytes(), original)

    def test_url_does_not_infer_capture_or_submission(self):
        path = self.init()
        self.run_cli("new", path, "Acme", "Lead", "--url", "https://example.com/1")
        data = json.loads((path / "applications/acme_lead/application.json").read_text())
        self.assertIsNone(data["source"]["captured_at"])
        self.assertEqual(data["submission"], {"status": "not_started", "submitted_at": None, "confirmation": None})

    def test_source_manifest_accepts_directory_and_file(self):
        path = self.init()
        (path / "evidence/career.md").write_text("Facts", encoding="utf-8")
        entries = [
            {"id": "career", "path": "evidence/career.md", "kind": "evidence", "priority": 1, "note": "Verified"},
            {"id": "corpus", "path": "evidence", "kind": "evidence", "priority": 2},
        ]
        (path / "profile/sources.json").write_text(json.dumps(entries))
        self.run_cli("doctor", path)
        output, _ = self.run_cli("inspect", path, "--json")
        self.assertEqual(json.loads(output)["sources"], 2)

    def test_source_path_traversal_absolute_and_windows_paths_rejected(self):
        path = self.init()
        for invalid in ("../outside", str(self.root / "packaged-assets/about.md"), "evidence/../profile/about.md", "C:\\outside\\file.md"):
            with self.subTest(path=invalid):
                entries = [{"id": "bad", "path": invalid, "kind": "evidence", "priority": 1}]
                (path / "profile/sources.json").write_text(json.dumps(entries))
                self.run_cli("doctor", path, success=False)
                self.run_cli("new", path, "Acme", "Lead", success=False)
        self.assertEqual(list((path / "applications").iterdir()), [])

    def test_source_external_symlink_and_nested_external_link_rejected(self):
        path = self.init()
        external = self.root / "outside.md"
        external.write_text("Other person's data")
        link = path / "evidence/link.md"
        link.symlink_to(external)
        for source in ("evidence/link.md", "evidence"):
            with self.subTest(source=source):
                (path / "profile/sources.json").write_text(json.dumps([
                    {"id": "bad", "path": source, "kind": "evidence", "priority": 1},
                ]))
                self.run_cli("doctor", path, success=False)

    def test_profile_external_symlink_rejected(self):
        path = self.init()
        about = path / "profile/about.md"
        about.unlink()
        about.symlink_to(self.assets / "about.md")
        self.run_cli("doctor", path, success=False)

    def test_internal_directory_link_cannot_hide_external_symlink(self):
        path = self.init()
        other = path / "other"
        other.mkdir()
        (other / "hidden.md").symlink_to(self.assets / "about.md")
        (path / "evidence/internal").symlink_to(other, target_is_directory=True)
        (path / "profile/sources.json").write_text(json.dumps([
            {"id": "corpus", "path": "evidence", "kind": "evidence", "priority": 1},
        ]))
        self.run_cli("doctor", path, success=False)

    def test_internal_directory_cycle_does_not_hang(self):
        path = self.init()
        (path / "evidence/loop").symlink_to(path / "evidence", target_is_directory=True)
        (path / "profile/sources.json").write_text(json.dumps([
            {"id": "corpus", "path": "evidence", "kind": "evidence", "priority": 1},
        ]))
        self.run_cli("doctor", path)

    def test_app_files_cannot_escape_app_folder(self):
        path = self.init()
        self.run_cli("new", path, "Acme", "Lead")
        manifest = path / "applications/acme_lead/application.json"
        data = json.loads(manifest.read_text())
        data["files"]["jd"] = "../../profile/about.md"
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path, success=False)

    def test_application_identity_mismatch_rejected(self):
        path = self.init()
        self.run_cli("new", path, "Acme", "Lead")
        manifest = path / "applications/acme_lead/application.json"
        data = json.loads(manifest.read_text())
        data["candidate"]["name"] = "Another Person"
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path, success=False)

    def test_bad_jd_or_url_cannot_leave_partial_application(self):
        path = self.init()
        self.run_cli("new", path, "Acme", "Lead", "--jd", self.root / "missing.md", success=False)
        self.run_cli("new", path, "Acme", "Lead", "--url", "javascript:alert(1)", success=False)
        self.assertEqual(list((path / "applications").iterdir()), [])

    def test_import_can_preserve_unknown_role_and_submission(self):
        path = self.init()
        self.run_cli("new", path, "Legacy", "Folder")
        manifest = path / "applications/legacy_folder/application.json"
        data = json.loads(manifest.read_text())
        data.update({"company": None, "role": None, "status": "unknown", "migration": {"imported_at": rolekit.now()}})
        data["submission"]["status"] = "unknown"
        (manifest.parent / "cv.html").write_text("Historical CV")
        (manifest.parent / "cv.pdf").write_bytes(b"Historical PDF, not freshly validated")
        data["files"].update({"cv_html": "cv.html", "cv_pdf": "cv.pdf"})
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path)
        output, _ = self.run_cli("inspect", path, "--json")
        self.assertEqual(json.loads(output)["application_statuses"], {"unknown": 1})
        self.assertEqual(json.loads(output)["submission_statuses"], {"unknown": 1})

    def test_known_application_requires_company_and_role(self):
        path = self.init()
        self.run_cli("new", path, "Acme", "Lead")
        manifest = path / "applications/acme_lead/application.json"
        data = json.loads(manifest.read_text())
        data["company"] = None
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path, success=False)

    def test_submitted_needs_separate_submission_record_and_proof(self):
        path = self.init()
        self.run_cli("new", path, "Acme", "Lead")
        manifest = path / "applications/acme_lead/application.json"
        data = json.loads(manifest.read_text())
        data["status"] = "submitted"
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path, success=False)
        data["submission"]["status"] = "submitted"
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path, success=False)
        data["submission"]["submitted_at"] = rolekit.now()
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path, success=False)
        data["submission"]["confirmation"] = "Provider receipt application #123; saved in submission.md"
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path)
        data["submission"]["submitted_at"] = "2026-10-15T12:00:00"
        manifest.write_text(json.dumps(data))
        self.run_cli("doctor", path, success=False)

    def test_unknown_source_kind_cannot_be_confused_with_evidence(self):
        path = self.init()
        (path / "profile/sources.json").write_text(json.dumps([
            {"id": "ambiguous", "path": "profile/about.md", "kind": "proof-maybe", "priority": 1},
        ]))
        self.run_cli("doctor", path, success=False)

    def test_malformed_enum_types_return_actionable_errors(self):
        path = self.init()
        self.run_cli("new", path, "Acme", "Lead")
        manifest = path / "applications/acme_lead/application.json"
        data = json.loads(manifest.read_text())
        data["status"] = []
        manifest.write_text(json.dumps(data))
        _, error = self.run_cli("doctor", path, success=False)
        self.assertIn("unknown application status", error)


class BrowserDiscoveryTests(unittest.TestCase):
    """Doctor must report the same browser readiness as the PDF renderer."""

    def browser(self, *, environment=None, executables=(), path_commands=None):
        commands = path_commands or {}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(rolekit.os.environ, environment or {}, clear=True))
            stack.enter_context(mock.patch.object(rolekit.Path, "home", return_value=Path("/profiles/tester")))
            stack.enter_context(mock.patch.object(rolekit.Path, "is_file", autospec=True, side_effect=lambda item: str(item) in executables))
            stack.enter_context(mock.patch.object(rolekit.os, "access", side_effect=lambda item, mode: str(item) in executables))
            lookup = stack.enter_context(mock.patch.object(rolekit.shutil, "which", side_effect=lambda name: commands.get(name)))
            result = rolekit.browser_path()
            queries = [call.args[0] for call in lookup.call_args_list]
        return result, queries

    def test_path_command_override_and_precedence(self):
        result, queries = self.browser(
            environment={"ROLEKIT_CHROME": "custom-chrome", "CHROME_BIN": "another-chrome"},
            path_commands={"custom-chrome": "/tools/browser"},
        )
        self.assertEqual(result, "/tools/browser")
        self.assertEqual(queries, ["custom-chrome"])

    def test_override_expands_environment_and_home(self):
        result, queries = self.browser(
            environment={"CHROME_BIN": "$BROWSER_ROOT/chrome", "BROWSER_ROOT": "/tools"},
            path_commands={"/tools/chrome": "/tools/chrome"},
        )
        self.assertEqual(result, "/tools/chrome")
        self.assertEqual(queries, ["/tools/chrome"])
        result, queries = self.browser(
            environment={"CHROME_BIN": "~/browser", "HOME": "/profiles/tester"},
            path_commands={"/profiles/tester/browser": "/profiles/tester/browser"},
        )
        self.assertEqual(result, "/profiles/tester/browser")
        self.assertEqual(queries, ["/profiles/tester/browser"])

    def test_invalid_override_does_not_fall_back_to_known_installation(self):
        result, queries = self.browser(
            environment={"ROLEKIT_CHROME": "missing", "CHROME_BIN": "working"},
            executables={"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"},
            path_commands={"working": "/tools/working"},
        )
        self.assertIsNone(result)
        self.assertEqual(queries, ["missing"])

    def test_windows_standard_installation_roots(self):
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            with self.subTest(variable=variable):
                executable = "/windows/programs/Google/Chrome/Application/chrome.exe"
                result, _ = self.browser(environment={variable: "/windows/programs"}, executables={executable})
                self.assertEqual(result, executable)

    def test_mac_user_installation_precedes_path_fallback(self):
        executable = "/profiles/tester/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        result, _ = self.browser(executables={executable, "/tools/chromium"}, path_commands={"chromium": "/tools/chromium"})
        self.assertEqual(result, executable)

    def test_path_chrome_exe_is_supported(self):
        result, queries = self.browser(executables={"/tools/chrome.exe"}, path_commands={"chrome.exe": "/tools/chrome.exe"})
        self.assertEqual(result, "/tools/chrome.exe")
        self.assertIn("chrome.exe", queries)

    def test_edge_is_not_auto_discovered(self):
        result, queries = self.browser(
            executables={"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/tools/msedge"},
            path_commands={"msedge": "/tools/msedge"},
        )
        self.assertIsNone(result)
        self.assertNotIn("msedge", queries)


if __name__ == "__main__":
    unittest.main()
