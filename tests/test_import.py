"""Exercise a real legacy import against a small synthetic filesystem."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

IMPORTER = Path(__file__).resolve().parents[1] / 'tools/import_personal_brain.py'


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'old'
        self.output = self.base / 'new'
        files = {
            'personal/about.md': '# Synthetic Person\nConfirmed source biography.\n',
            'work/cv/_template/master_cv.html': '<html><head><link rel="stylesheet" href="style.css"></head><body>Example master</body></html>',
            'work/cv/_template/skills_truth.md': '# Claim guardrails\nOnly supported facts.\n',
            'work/cv/_template/style.css': 'body { color: #111; }',
            'work/cv/example-role/jd.md': '# Full posting\nAll responsibilities and qualifications.\n',
            'work/cv/example-role/cv.html': '<html><head><link rel="stylesheet" href="../_template/style.css"></head><body>Example person</body></html>',
            'work/cv/example-role/cv.pdf': 'historical synthetic PDF bytes',
            'work/tiktok/sources/docs/source.md': '# Supporting result\nMeasured project outcome.\n',
        }
        for relative, text in files.items():
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
        perf = self.source / 'work/tiktok/projects/lawsuit/sources/docs/perf'
        perf.mkdir(parents=True)
        (perf / 'period.md').symlink_to(self.source / 'work/tiktok/sources/docs/source.md')

    def run_import(self, *extra, success=True):
        result = subprocess.run([sys.executable, str(IMPORTER), '--source', str(self.source),
                                 '--workspace', str(self.output), '--name', 'Synthetic Person', *extra],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        return result

    def test_import_preserves_sources_and_stands_alone(self):
        before = hashes(self.source)
        self.run_import()
        self.assertEqual(hashes(self.source), before)
        copied_link = self.output / 'evidence/legacy/work/tiktok/projects/lawsuit/sources/docs/perf/period.md'
        self.assertFalse(copied_link.is_symlink())
        self.assertEqual(copied_link.read_bytes(), (self.source / 'work/tiktok/sources/docs/source.md').read_bytes())
        application = self.output / 'applications/example-role'
        data = json.loads((application / 'application.json').read_text())
        self.assertEqual(data['status'], 'unknown')
        self.assertEqual(data['submission']['status'], 'unknown')
        self.assertEqual((application / 'jd.md').read_bytes(), (self.source / 'work/cv/example-role/jd.md').read_bytes())
        self.assertIn('<style>', (application / 'cv.html').read_text())
        # With the original entirely absent, verification still works.
        self.source.rename(self.base / 'unavailable')
        result = subprocess.run([sys.executable, str(IMPORTER), '--workspace', str(self.output), '--verify'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verification_detects_snapshot_tampering(self):
        self.run_import()
        target = self.output / 'evidence/legacy/work/cv/example-role/jd.md'
        target.write_text('changed', encoding='utf-8')
        result = self.run_import('--verify', success=False)
        self.assertIn('Snapshot differs:', result.stderr)
        self.assertIn('All responsibilities', (self.source / 'work/cv/example-role/jd.md').read_text())

    def test_import_does_not_overwrite_a_workspace(self):
        self.run_import()
        before = hashes(self.output)
        self.run_import(success=False)
        self.assertEqual(hashes(self.output), before)


if __name__ == '__main__':
    unittest.main()
