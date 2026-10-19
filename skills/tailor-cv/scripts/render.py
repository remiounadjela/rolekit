#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf==6.20.1"]
# ///
"""Render a self-contained CV to a verified one-page PDF using local Chrome.

Run python render_auto.py APPLICATION_FOLDER [--style FILE]. The input is cv.html. On success,
cv.html contains the chosen inline stylesheet, cv.pdf contains one readable page,
and render.json records artifact hashes. On failure existing HTML/PDF stay intact
and render.json is marked failed. No network resources are permitted.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

from pypdf import PdfReader


SCALES = (1.00, 0.97, 0.94, 0.91, 0.88, 0.85)
HERE = Path(__file__).resolve().parent
DEFAULT_STYLE = HERE.parent / "assets" / "style.css"
STYLE_ID = "rolekit-print-style"
CSP_ID = "rolekit-render-csp"
CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; "
    "script-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'"
)


class RenderError(Exception):
    """An actionable error that should not replace previously generated artifacts."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_css(css: str) -> None:
    """Keep CSS self-contained; escapes are rejected to prevent URL obfuscation."""
    clean = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if "\\" in clean:
        raise RenderError("CSS escapes are unsupported; use plain CSS and embedded data: assets.")
    if re.search(r"@import\b", clean, re.I):
        raise RenderError("CSS @import is forbidden; inline the stylesheet instead.")
    if re.search(r"</style", css, re.I):
        raise RenderError("The stylesheet contains an unexpected </style> tag.")
    # Reject uncommon resource functions as well as ordinary external url().
    if re.search(r"\b(?:image-set|src)\s*\(", clean, re.I):
        raise RenderError("CSS image-set()/src() resources are unsupported; use embedded data: assets.")
    for match in re.finditer(r"\burl\s*\((.*?)\)", clean, re.I | re.S):
        target = match.group(1).strip().strip("\"'").strip()
        if not target.lower().startswith("data:"):
            raise RenderError(f"CSS resource must be embedded as data:, found {target[:100]!r}.")


class StandaloneHTML(HTMLParser):
    """Preserve markup while removing stylesheets and validating loaded resources."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.skip_style = False
        self.in_style = False
        self.style_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, True)

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], closed: bool) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "style" and values.get("id") == STYLE_ID:
            self.skip_style = not closed
            return
        if self.skip_style:
            return
        if tag == "link":
            if "stylesheet" in values.get("rel", "").lower().split():
                return
            raise RenderError("HTML <link> resources are unsupported; embed required assets.")
        if tag == "meta" and values.get("id") == CSP_ID:
            return
        if tag in {"script", "iframe", "frame", "object", "embed", "base", "audio", "video"}:
            raise RenderError(f"HTML <{tag}> is unsupported in a static CV.")
        if tag == "meta" and values.get("http-equiv", "").lower() in {
            "refresh", "content-security-policy", "set-cookie"
        }:
            raise RenderError("HTML redirects and custom security policies are unsupported.")
        for key, value in values.items():
            if key.startswith("on"):
                raise RenderError(f"HTML event handler {key!r} is unsupported.")
            if key in {"srcset", "ping", "background", "manifest", "action", "formaction"}:
                raise RenderError(f"HTML resource attribute {key!r} is unsupported.")
            if key in {"src", "poster"} or (key in {"href", "xlink:href"} and tag != "a"):
                if value and not value.lower().startswith(("data:", "#")):
                    raise RenderError(f"HTML <{tag}> resource must be embedded as data:.")
            if key == "href" and tag == "a" and re.match(r"\s*(?:javascript|data):", value, re.I):
                raise RenderError("Active or data: anchor links are unsupported.")
            if key == "style":
                check_css(value)
        self.parts.append(self.get_starttag_text())
        if tag == "style" and not closed:
            self.in_style = True
            self.style_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self.skip_style:
            if tag == "style":
                self.skip_style = False
            return
        if tag == "style" and self.in_style:
            check_css("".join(self.style_parts))
            self.in_style = False
        if tag != "link":
            self.parts.append(f"</{tag}>")

    def _text(self, value: str) -> None:
        if not self.skip_style:
            self.parts.append(value)
            if self.in_style:
                self.style_parts.append(value)

    def handle_data(self, data: str) -> None:
        self._text(data)

    def handle_entityref(self, name: str) -> None:
        self._text(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._text(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._text(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._text(f"<!{decl}>")


def prepare_html(source: str) -> str:
    parser = StandaloneHTML()
    parser.feed(source)
    parser.close()
    if parser.skip_style or parser.in_style:
        raise RenderError("HTML contains an unclosed <style> element.")
    return "".join(parser.parts)


def build(source: str, css: str, scale: float) -> str:
    """Add security policy at the start of head and print CSS at its end."""
    policy = f'<meta id="{CSP_ID}" http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}">'
    style = f'<style id="{STYLE_ID}">\n{css}\n:root {{ --scale: {scale:.2f}; }}\n</style>'
    head = re.search(r"<head\b[^>]*>", source, re.I)
    close = re.search(r"</head\s*>", source, re.I)
    if head and close and close.start() >= head.end():
        return source[:head.end()] + policy + source[head.end():close.start()] + style + source[close.start():]
    if head or close:
        raise RenderError("HTML must have both <head> and </head>, or neither.")
    html_tag = re.search(r"<html\b[^>]*>", source, re.I)
    if html_tag:
        return source[:html_tag.end()] + f"<head><meta charset='utf-8'>{policy}{style}</head>" + source[html_tag.end():]
    return f"<!doctype html><html><head><meta charset='utf-8'>{policy}{style}</head><body>{source}</body></html>"


def discover_chrome() -> Path:
    """Resolve explicit overrides, common installations, then executable PATH names."""
    for key in ("ROLEKIT_CHROME", "CHROME_BIN"):
        if os.environ.get(key):
            value = os.path.expandvars(os.path.expanduser(os.environ[key]))
            found = shutil.which(value)
            if found:
                return Path(found).resolve()
            raise RenderError(f"{key} does not point to an executable Chrome/Chromium: {value}")
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(key):
            base = Path(os.environ[key])
            candidates.extend((base / "Google/Chrome/Application/chrome.exe", base / "Chromium/Application/chrome.exe"))
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "chrome.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise RenderError("Chrome/Chromium was not found. Install it or set ROLEKIT_CHROME to its executable path.")


def stop_browser(process: subprocess.Popen) -> None:
    """Stop the whole temporary browser process group, including timed-out children."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.communicate()


def render_one(chrome: Path, html: Path, pdf: Path, profile: Path, timeout: float) -> None:
    command = [
        str(chrome), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--disable-background-networking", "--disable-component-update", "--disable-sync",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        "--disable-default-apps", "--disable-domain-reliability",
        "--proxy-server=http://127.0.0.1:9", "--host-resolver-rules=MAP * ~NOTFOUND",
        f"--user-data-dir={profile}", f"--print-to-pdf={pdf}", html.as_uri(),
    ]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        command.insert(1, "--no-sandbox")
    kwargs = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
    }
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    try:
        _, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stop_browser(process)
        raise RenderError(f"Chrome timed out after {timeout:g} seconds; no artifacts were replaced.") from exc
    except BaseException:
        stop_browser(process)
        raise
    if process.returncode or not pdf.is_file():
        detail = stderr.decode("utf-8", errors="replace")[-1500:].strip()
        raise RenderError(f"Chrome failed to produce a PDF (exit {process.returncode}). {detail}")


def atomic_json(path: Path, report: dict) -> None:
    """Use a neighboring staging file so replacing a report stays atomic."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".render-", suffix=".json", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run(folder: Path, style: Path, timeout: float) -> dict:
    """Verify staged candidates, then commit HTML/PDF and their hash report."""
    folder, style = folder.resolve(), style.resolve()
    if not folder.is_dir():
        raise RenderError(f"Application folder does not exist: {folder}")
    html_path, pdf_path, report_path = (folder / name for name in ("cv.html", "cv.pdf", "render.json"))
    started = datetime.now(timezone.utc).isoformat()
    attempts: list[dict] = []
    source_hash = None
    try:
        # Invalidate a previous success before validation or browser work can fail.
        atomic_json(report_path, {"schema_version": 1, "status": "in_progress", "started_at": started})
        if not html_path.is_file():
            raise RenderError(f"No cv.html found in {folder}")
        source_bytes = html_path.read_bytes()
        source_hash = digest(source_bytes)
        source = prepare_html(source_bytes.decode("utf-8"))
        if not style.is_file():
            raise RenderError(f"Stylesheet does not exist: {style}")
        style_bytes = style.read_bytes()
        css = style_bytes.decode("utf-8")
        check_css(css)
        chrome = discover_chrome()
        with tempfile.TemporaryDirectory(prefix=".rolekit-render-", dir=folder) as temporary:
            staging = Path(temporary)
            candidate_html, candidate_pdf = staging / "cv.html", staging / "cv.pdf"
            for scale in SCALES:
                rendered = build(source, css, scale)
                candidate_html.write_text(rendered, encoding="utf-8")
                candidate_pdf.unlink(missing_ok=True)
                render_one(chrome, candidate_html, candidate_pdf, staging / "chrome-profile", timeout)
                try:
                    reader = PdfReader(str(candidate_pdf))
                    pages = len(reader.pages)
                    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
                except Exception as exc:
                    raise RenderError(f"The generated PDF could not be verified: {exc}") from exc
                attempts.append({"scale": scale, "pages": pages, "text_characters": len(extracted.strip())})
                if pages == 1 and extracted.strip():
                    html_bytes, pdf_bytes = candidate_html.read_bytes(), candidate_pdf.read_bytes()
                    report = {
                        "schema_version": 1, "status": "verified", "verified_at": datetime.now(timezone.utc).isoformat(),
                        "started_at": started, "page_count": pages, "scale": scale,
                        "text_characters": len(extracted.strip()), "source_html_sha256": source_hash,
                        "html_sha256": digest(html_bytes), "pdf_sha256": digest(pdf_bytes),
                        "style_sha256": digest(style_bytes), "style_path": str(style),
                        "chrome_path": str(chrome), "attempts": attempts,
                    }
                    # Stage on the same filesystem. Restore both prior artifacts if any commit step fails.
                    old_pdf = pdf_path.read_bytes() if pdf_path.exists() else None
                    try:
                        os.replace(candidate_html, html_path)
                        os.replace(candidate_pdf, pdf_path)
                        atomic_json(report_path, report)
                    except Exception:
                        html_path.write_bytes(source_bytes)
                        if old_pdf is None:
                            pdf_path.unlink(missing_ok=True)
                        else:
                            pdf_path.write_bytes(old_pdf)
                        raise
                    return report
                if not extracted.strip():
                    raise RenderError("The generated PDF has no extractable text; use real HTML text for the CV.")
                print(f"… {pages} pages at scale={scale:.2f}; tightening", file=sys.stderr)
        raise RenderError("CV still exceeds one page at scale=0.85. Trim content and run again.")
    except BaseException as exc:
        atomic_json(report_path, {
            "schema_version": 1, "status": "failed", "started_at": started,
            "failed_at": datetime.now(timezone.utc).isoformat(), "error": str(exc),
            "source_html_sha256": source_hash, "attempts": attempts,
        })
        if isinstance(exc, (RenderError, KeyboardInterrupt)):
            raise
        raise RenderError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("application_folder", type=Path, help="folder containing cv.html; output stays in this folder")
    parser.add_argument("--style", type=Path, default=DEFAULT_STYLE, help="print CSS file (default: skill assets/style.css)")
    parser.add_argument("--timeout", type=float, default=45, metavar="SECONDS", help="Chrome timeout per scale attempt (default: 45)")
    parser.add_argument("--max-pages", type=int, choices=[1], default=1, help="required page count; only 1 is supported")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        report = run(args.application_folder, args.style, args.timeout)
    except (RenderError, OSError) as exc:
        print(f"Render failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified one page → {args.application_folder.resolve() / 'cv.pdf'} (scale={report['scale']:.2f})")
    print("HTML/PDF/style hashes and verification details → render.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
