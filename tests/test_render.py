"""Portable renderer checks. Run: uv run --with 'pypdf==6.20.1' python -m unittest discover -s tests."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rolekit_render", ROOT / "skills/tailor-cv/scripts/render.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def make_pdf(path, pages=1, text="A meaningful CV"):
    """Write real PDF text streams so pypdf verification is exercised."""
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as output:
        writer.write(output)


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.html = self.folder / "cv.html"
        self.pdf = self.folder / "cv.pdf"
        self.style = self.folder / "style.css"
        self.original = '<!doctype html><html><head></head><body><h1>Test Candidate</h1><p>Evidence backed work.</p></body></html>'
        self.html.write_text(self.original)
        self.style.write_text(':root { --scale: 1; } html { font-size: calc(10pt * var(--scale)); }')

    def tearDown(self):
        self.temporary.cleanup()

    def report(self):
        return json.loads((self.folder / "render.json").read_text())

    def run_with(self, fake):
        with patch.object(renderer, "discover_chrome", return_value=Path("/fake/chrome")), patch.object(renderer, "render_one", side_effect=fake):
            return renderer.run(self.folder, self.style, 1)

    def test_external_stylesheets_removed_and_previous_injection_replaced(self):
        source = '<html><head><link rel="stylesheet" href="https://example.com/a.css"><style id="rolekit-print-style">old</style></head><body><a href="https://example.com">Website</a></body></html>'
        clean = renderer.prepare_html(source)
        first = renderer.build(clean, "h1 { color: black; }", 0.94)
        second = renderer.build(renderer.prepare_html(first), "h1 { color: black; }", 0.91)
        self.assertNotIn("a.css", second)
        self.assertNotIn(">old<", second)
        self.assertEqual(second.count('id="rolekit-print-style"'), 1)
        self.assertEqual(second.count('id="rolekit-render-csp"'), 1)
        self.assertIn("--scale: 0.91", second)
        self.assertIn('href="https://example.com"', second)

    def test_headless_fragments_and_existing_empty_head_are_supported(self):
        for source in ("<h1>Candidate</h1>", self.original, "<html><body>Candidate</body></html>"):
            with self.subTest(source=source):
                output = renderer.build(renderer.prepare_html(source), "body {color:black}", 1)
                self.assertEqual(output.lower().count("<head>"), 1)
                self.assertIn("Content-Security-Policy", output)

    def test_loaded_resources_and_active_content_rejected(self):
        for source in ('<img src="https://example.com/photo.jpg">', '<img src="file:///private/photo.jpg">', '<script>alert(1)</script>', '<div onclick="fetch(1)">x</div>', '<iframe src="https://example.com"></iframe>', '<meta http-equiv="refresh" content="0;url=https://example.com">', '<div style="background:url(https://example.com/a)">x</div>', '<style>@import "https://example.com/a.css";</style>'):
            with self.subTest(source=source), self.assertRaises(renderer.RenderError):
                renderer.prepare_html(source)

    def test_css_remote_loads_and_obfuscation_rejected(self):
        for css in ('body {background: url(https://example.com/x)}', '@im/**/port "remote";', r'body {background: u\72l("remote")}', 'body {background:image-set("remote" 1x)}'):
            with self.subTest(css=css), self.assertRaises(renderer.RenderError):
                renderer.check_css(css)
        renderer.check_css('body {background:url("data:image/png;base64,AA==")}')
        renderer.prepare_html('<img src="data:image/png;base64,AA=="><svg><use href="#local"></use></svg>')

    def test_autofit_exact_steps_and_hashes_use_final_artifacts(self):
        scales = []

        def fake(chrome, html, pdf, profile, timeout):
            content = html.read_text()
            scale = next(value for value in renderer.SCALES if f"--scale: {value:.2f};" in content)
            scales.append(scale)
            make_pdf(pdf, pages=2 if scale > 0.91 else 1)

        report = self.run_with(fake)
        self.assertEqual(scales, [1.00, 0.97, 0.94, 0.91])
        self.assertEqual(report["status"], "verified")
        self.assertEqual(len(PdfReader(self.pdf).pages), 1)
        for key, path in (("html_sha256", self.html), ("pdf_sha256", self.pdf), ("style_sha256", self.style)):
            self.assertEqual(report[key], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(self.report(), report)
        self.assertFalse(list(self.folder.glob(".rolekit-render-*")))

    def test_oversize_preserves_existing_html_pdf_and_invalidates_success(self):
        self.pdf.write_bytes(b"prior pdf")
        (self.folder / "render.json").write_text('{"status":"verified"}')
        scales = []

        def fake(chrome, html, pdf, profile, timeout):
            scales.append(html.read_text())
            make_pdf(pdf, pages=2)

        with self.assertRaisesRegex(renderer.RenderError, "Trim content"):
            self.run_with(fake)
        self.assertEqual(len(scales), 6)
        self.assertEqual(self.html.read_text(), self.original)
        self.assertEqual(self.pdf.read_bytes(), b"prior pdf")
        self.assertEqual(self.report()["status"], "failed")
        self.assertNotIn("pdf_sha256", self.report())
        self.assertFalse(list(self.folder.glob(".rolekit-render-*")))

    def test_empty_text_pdf_fails_without_replacing_prior_artifacts(self):
        self.pdf.write_bytes(b"prior pdf")

        def fake(chrome, html, pdf, profile, timeout):
            make_pdf(pdf, text="")

        with self.assertRaisesRegex(renderer.RenderError, "no extractable text"):
            self.run_with(fake)
        self.assertEqual(self.pdf.read_bytes(), b"prior pdf")
        self.assertEqual(self.html.read_text(), self.original)
        self.assertEqual(self.report()["status"], "failed")

    def test_browser_timeout_is_a_preserving_failure(self):
        self.pdf.write_bytes(b"prior pdf")
        with self.assertRaisesRegex(renderer.RenderError, "timed out"):
            self.run_with(lambda *args: (_ for _ in ()).throw(renderer.RenderError("Chrome timed out")))
        self.assertEqual(self.pdf.read_bytes(), b"prior pdf")
        self.assertEqual(self.html.read_text(), self.original)
        self.assertEqual(self.report()["status"], "failed")

    def test_invalid_explicit_browser_does_not_silently_fallback(self):
        with patch.dict(os.environ, {"ROLEKIT_CHROME": "/path/that/does/not/exist"}):
            with self.assertRaisesRegex(renderer.RenderError, "ROLEKIT_CHROME"):
                renderer.discover_chrome()


if __name__ == "__main__":
    unittest.main()
