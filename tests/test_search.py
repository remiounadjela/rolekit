"""Candidate isolation and exactly-once attempt safety for the local search ledger."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/job-search/scripts/search.py"
SPEC = importlib.util.spec_from_file_location("rolekit_search", SCRIPT)
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


class URLIdentityTests(unittest.TestCase):
    def test_ashby_application_overview_and_tracking_share_identity(self):
        urls = ["https://jobs.ashbyhq.com/acme/8c226d48-6143-49a3-9c32-9fc20f631a44",
                "http://jobs.ashbyhq.com/acme/8C226D48-6143-49A3-9C32-9FC20F631A44/application?utm_source=x&source=newsletter",
                "https://jobs.ashbyhq.com/acme/8c226d48-6143-49a3-9c32-9fc20f631a44/overview/#apply"]
        self.assertEqual(len({search.job_key(url) for url in urls}), 1)

    def test_greenhouse_alias_and_embed_share_identity(self):
        urls = ["https://boards.greenhouse.io/acme/jobs/123?gh_src=abc",
                "https://job-boards.greenhouse.io/acme/jobs/123/",
                "https://boards.greenhouse.io/embed/job_app?for=acme&token=123&utm_source=x"]
        self.assertEqual(len({search.job_key(url) for url in urls}), 1)
        self.assertNotEqual(search.job_key(urls[0]), search.job_key(urls[0].replace("/123", "/456")))

    def test_generic_semantic_parameters_preserved(self):
        first = "https://careers.example/jobs?jobId=123&source=internal&x=1&x=2"
        reordered = "https://careers.example/jobs?x=2&source=internal&x=1&jobId=123&utm_campaign=z"
        self.assertEqual(search.job_key(first), search.job_key(reordered))
        self.assertNotEqual(search.job_key(first), search.job_key(first.replace("123", "456")))
        self.assertIn("source=internal", search.canonical_url(first))
        self.assertNotEqual(search.job_key("https://example.com/#/jobs/1"), search.job_key("https://example.com/#/jobs/2"))

    def test_invalid_or_credential_urls_rejected(self):
        for value in (None, "", "javascript:bad", "/relative", "https://user:secret@example.com/", "https://example.com:bad/"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                search.canonical_url(value)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.make_workspace("alice", "Alice Example")

    def make_workspace(self, slug, name):
        workspace = self.root / slug
        workspace.mkdir()
        (workspace / "rolekit.json").write_text(json.dumps({"candidate": {"name": name}, "applications": "applications"}))
        (workspace / "applications").mkdir()
        return workspace

    def cli(self, *args, success=True):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = search.main(list(map(str, args)))
        self.assertEqual(code, 0 if success else 1, (output.getvalue(), error.getvalue()))
        return json.loads(output.getvalue()) if success else error.getvalue()

    def ingest(self, workspace=None, **updates):
        item = {"company": "Acme", "title": "AI Lead", "url": "https://jobs.ashbyhq.com/acme/job-id", **updates}
        path = self.root / "items.json"
        path.write_text(json.dumps([item]))
        return self.cli("ingest", workspace or self.workspace, "--items", path)

    def evidence(self, workspace=None, name="receipt.md"):
        path = (workspace or self.workspace) / name
        path.write_text("Provider confirmation application 123, read back from confirmation page.")
        return path

    def test_repeat_ingest_preserves_identity_metadata_and_state(self):
        original = self.ingest()
        self.assertEqual(original["inserted"], 1)
        key = original["jobs"][0]["job_key"]
        self.cli("begin-attempt", self.workspace, key)
        self.cli("resolve-attempt", self.workspace, key, "--status", "unknown", "--evidence", self.evidence())
        repeated = self.ingest(company="Changed", title="Changed", url="https://jobs.ashbyhq.com/acme/job-id/application?source=x")
        self.assertEqual((repeated["inserted"], repeated["existing"]), (0, 1))
        job = repeated["jobs"][0]
        self.assertEqual((job["company"], job["title"], job["status"]), ("Acme", "AI Lead", "unknown"))
        self.assertEqual(job["job_key"], key)

    def test_concurrent_begin_only_one_can_lock(self):
        key = self.ingest()["jobs"][0]["job_key"]
        args = [sys.executable, str(SCRIPT), "begin-attempt", str(self.workspace), key]
        first = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        first.communicate(timeout=15)
        second.communicate(timeout=15)
        self.assertEqual(sorted((first.returncode, second.returncode)), [0, 1])
        job = self.cli("list", self.workspace)[0]
        self.assertEqual(job["status"], "submitting")
        self.assertEqual(len(job["attempts"]), 1)
        self.cli("begin-attempt", self.workspace, key, success=False)

    def test_unknown_blocks_retry_but_can_be_confirmed_without_resending(self):
        key = self.ingest()["jobs"][0]["job_key"]
        self.cli("begin-attempt", self.workspace, key)
        proof = self.evidence()
        self.cli("resolve-attempt", self.workspace, key, "--status", "unknown", "--evidence", proof)
        self.cli("begin-attempt", self.workspace, key, success=False)
        self.cli("resolve-attempt", self.workspace, key, "--status", "blocked", "--pre-submit", "--evidence", proof, success=False)
        result = self.cli("resolve-attempt", self.workspace, key, "--status", "submitted", "--evidence", proof)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual([entry["status"] for entry in result["attempts"][0]["outcomes"]], ["unknown", "submitted"])
        self.cli("begin-attempt", self.workspace, key, success=False)

    def test_blocked_requires_explicit_no_submit_assertion(self):
        key = self.ingest()["jobs"][0]["job_key"]
        self.cli("begin-attempt", self.workspace, key)
        proof = self.evidence()
        self.cli("resolve-attempt", self.workspace, key, "--status", "blocked", "--evidence", proof, success=False)
        result = self.cli("resolve-attempt", self.workspace, key, "--status", "blocked", "--pre-submit", "--evidence", proof)
        self.assertEqual(result["status"], "blocked")
        result = self.cli("begin-attempt", self.workspace, key)
        self.assertEqual(len(result["attempts"]), 2)

    def test_evidence_and_artifact_hashes_required_and_contained(self):
        key = self.ingest()["jobs"][0]["job_key"]
        artifact = self.evidence(name="cv.pdf")
        self.cli("begin-attempt", self.workspace, key, "--artifact", "missing.pdf", success=False)
        result = self.cli("begin-attempt", self.workspace, key, "--artifact", artifact)
        self.assertEqual(result["attempts"][0]["artifacts"], [search.proof(self.workspace, artifact)])
        outside = self.root / "other-person.txt"
        outside.write_text("Other candidate data")
        (self.workspace / "escape.md").symlink_to(outside)
        for path in (outside, "../other-person.txt", "escape.md", "missing.md", "."):
            self.cli("resolve-attempt", self.workspace, key, "--status", "submitted", "--evidence", path, success=False)
        receipt = self.evidence()
        result = self.cli("resolve-attempt", self.workspace, key, "--status", "submitted", "--evidence", "receipt.md")
        self.assertEqual(result["attempts"][0]["evidence"], search.proof(self.workspace, receipt))

    def test_explicit_workspace_and_database_candidate_isolation(self):
        missing = self.root / "missing"
        self.cli("list", missing, success=False)
        self.assertFalse(missing.exists())
        self.ingest()
        bob = self.make_workspace("bob", "Bob Example")
        self.assertEqual(self.cli("list", bob), [])
        shutil.copyfile(self.workspace / "search/ledger.sqlite3", bob / "search/ledger.sqlite3")
        self.cli("list", bob, success=False)

    def test_external_search_symlink_rejected(self):
        other = self.root / "outside"
        other.mkdir()
        (self.workspace / "search").symlink_to(other, target_is_directory=True)
        self.cli("list", self.workspace, success=False)
        self.assertEqual(list(other.iterdir()), [])

    def test_legacy_submitted_and_unknown_bootstrap_before_begin(self):
        for slug, status in (("done", "submitted"), ("uncertain", "unknown"), ("draft", "not_started")):
            folder = self.workspace / "applications" / slug
            folder.mkdir()
            manifest = {"candidate": {"name": "Alice Example"}, "company": "Acme", "role": "Lead",
                        "source": {"url": f"https://boards.greenhouse.io/acme/jobs/{slug}"},
                        "submission": {"status": status}}
            (folder / "application.json").write_text(json.dumps(manifest))
        jobs = self.cli("list", self.workspace)
        self.assertEqual({job["status"] for job in jobs}, {"submitted", "unknown"})
        self.assertEqual(len(jobs), 2)
        for job in jobs:
            self.cli("begin-attempt", self.workspace, job["job_key"], success=False)
            self.assertEqual(job["attempts"][0]["origin"], "legacy")
        again = self.cli("list", self.workspace)
        self.assertEqual([len(job["attempts"]) for job in again], [1, 1])

    def test_bootstrap_cannot_downgrade_submitted_and_cross_candidate_rejected(self):
        folder = self.workspace / "applications/acme"
        folder.mkdir()
        manifest = folder / "application.json"
        data = {"source": {"url": "https://example.com/job/1"}, "submission": {"status": "unknown"}}
        manifest.write_text(json.dumps(data))
        key = self.cli("list", self.workspace)[0]["job_key"]
        self.cli("resolve-attempt", self.workspace, key, "--status", "submitted", "--evidence", self.evidence())
        data["role"] = "Changed legacy metadata"
        manifest.write_text(json.dumps(data))
        self.assertEqual(self.cli("list", self.workspace)[0]["status"], "submitted")
        data["candidate"] = {"name": "Bob Example"}
        manifest.write_text(json.dumps(data))
        self.cli("list", self.workspace, success=False)

    def test_new_legacy_confirmation_resolves_existing_pending_attempt(self):
        key = self.ingest()["jobs"][0]["job_key"]
        self.cli("begin-attempt", self.workspace, key)
        folder = self.workspace / "applications/acme"
        folder.mkdir()
        (folder / "application.json").write_text(json.dumps({
            "source": {"url": "https://jobs.ashbyhq.com/acme/job-id/application"},
            "submission": {"status": "submitted"}}))
        job = self.cli("list", self.workspace)[0]
        self.assertEqual(job["status"], "submitted")
        self.assertEqual(len(job["attempts"]), 1)
        self.assertEqual(job["attempts"][0]["status"], "submitted")

    def test_invalid_batch_does_not_partially_ingest(self):
        path = self.root / "items.json"
        path.write_text(json.dumps([{"company": "Acme", "title": "Lead", "url": "https://example.com/job/1"}, {"company": "Missing"}]))
        self.cli("ingest", self.workspace, "--items", path, success=False)
        self.assertFalse((self.workspace / "search").exists())


if __name__ == "__main__":
    unittest.main()
