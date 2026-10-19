#!/usr/bin/env python3
"""Small, local-only workspace helpers for RoleKit. Requires Python 3.10+."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import unicodedata
from urllib.parse import urlparse


PROFILE_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "profile"
PROFILE_FILES = ("about.md", "skills_truth.md", "master_cv.html", "style.css", "experiences.md", "review.md", "cv_style.md")
PROFILE_KEYS = ("about", "skills_truth", "master_cv", "style")
OPTIONAL_PROFILE_KEYS = ("experiences", "review", "cv_style")
APPLICATION_STATUSES = {
    "draft", "ready_for_review", "approved", "submitted", "blocked", "rejected",
    "withdrawn", "interviewing", "offer", "unknown",
}
SUBMISSION_STATUSES = {"not_started", "prepared", "authorized", "submitted", "blocked", "unknown"}
SOURCE_KINDS = {"evidence", "context", "example", "legacy"}


class WorkspaceError(ValueError):
    """An actionable configuration or path error."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"Cannot read {path}: {exc}") from exc


def write_json(path: Path, value) -> None:
    # Exclusive creation matters: no existing application or configuration is replaced.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def nonempty(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(f"{label} must be a nonempty string")
    return value


def contained(base: Path, value, label: str, *, exists: bool = True) -> Path:
    """Resolve a portable, relative path without allowing escape or traversal."""
    value = nonempty(value, label)
    if "\\" in value or "\x00" in value:
        raise WorkspaceError(f"{label} must use a relative path with '/' separators")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or re.match(r"^[A-Za-z]:", value):
        raise WorkspaceError(f"{label} must stay inside its root: {value!r}")
    try:
        root = base.resolve(strict=True)
        target = (root / relative).resolve(strict=exists)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError(f"Invalid {label}: {value!r}: {exc}") from exc
    if not target.is_relative_to(root):
        raise WorkspaceError(f"{label} points outside its root: {value!r}")
    return target


def check_nested_links(path: Path, root: Path, label: str) -> None:
    """A declared source directory must not hide links to outside evidence."""
    if not path.is_dir():
        return
    visited: set[Path] = set()
    for directory, directories, filenames in os.walk(path, followlinks=True):
        resolved = Path(directory).resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise WorkspaceError(f"External directory in {label}: {directory}")
        if resolved in visited:
            directories.clear()
            continue
        visited.add(resolved)
        for name in directories + filenames:
            item = Path(directory) / name
            if not item.is_symlink():
                continue
            try:
                target = item.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise WorkspaceError(f"Broken or cyclic symlink in {label}: {item}") from exc
            if not target.is_relative_to(root):
                raise WorkspaceError(f"External symlink in {label}: {item}")


def workspace(path: str | Path) -> tuple[Path, dict]:
    try:
        root = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError(f"Workspace does not exist: {path}") from exc
    if not root.is_dir():
        raise WorkspaceError(f"Workspace is not a directory: {root}")
    config_path = contained(root, "rolekit.json", "workspace configuration")
    config = read_json(config_path)
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config["schema_version"] != 1:
        raise WorkspaceError("rolekit.json must be an object with schema_version: 1")
    candidate = config.get("candidate")
    if not isinstance(candidate, dict):
        raise WorkspaceError("rolekit.json candidate must be an object")
    nonempty(candidate.get("name"), "candidate.name")
    defaults = config.get("defaults")
    limit = defaults.get("page_limit") if isinstance(defaults, dict) else None
    if type(limit) is not int or limit < 1:
        raise WorkspaceError("defaults.page_limit must be a positive integer")
    profile = config.get("profile")
    if not isinstance(profile, dict):
        raise WorkspaceError("rolekit.json profile must be an object of relative file paths")
    for key in PROFILE_KEYS + tuple(key for key in OPTIONAL_PROFILE_KEYS if key in profile):
        target = contained(root, profile.get(key), f"profile.{key}")
        if not target.is_file():
            raise WorkspaceError(f"profile.{key} must point to a file")
    sources = contained(root, config.get("sources"), "sources")
    if not sources.is_file():
        raise WorkspaceError("sources must point to a JSON file")
    applications = contained(root, config.get("applications"), "applications")
    if not applications.is_dir() or applications == root:
        raise WorkspaceError("applications must point to a directory within the workspace")
    return root, config


def load_sources(root: Path, config: dict) -> list[dict]:
    sources = read_json(contained(root, config["sources"], "sources"))
    if not isinstance(sources, list):
        raise WorkspaceError("sources manifest must be an array")
    seen = set()
    for index, entry in enumerate(sources):
        label = f"sources[{index}]"
        if not isinstance(entry, dict):
            raise WorkspaceError(f"{label} must be an object")
        identifier = nonempty(entry.get("id"), f"{label}.id")
        if identifier in seen:
            raise WorkspaceError(f"Duplicate source id: {identifier}")
        seen.add(identifier)
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in SOURCE_KINDS:
            raise WorkspaceError(f"{label}.kind must be evidence, context, example, or legacy")
        if type(entry.get("priority")) is not int:
            raise WorkspaceError(f"{label}.priority must be an integer")
        if "note" in entry and not isinstance(entry["note"], str):
            raise WorkspaceError(f"{label}.note must be a string")
        target = contained(root, entry.get("path"), f"{label}.path")
        if not (target.is_file() or target.is_dir()):
            raise WorkspaceError(f"{label}.path must be a file or directory")
        check_nested_links(target, root, label)
    return sources


def application_paths(root: Path, config: dict) -> list[Path]:
    applications = contained(root, config["applications"], "applications")
    check_nested_links(applications, root, "applications")
    return sorted(applications.glob("*/application.json"))


def load_application(path: Path, root: Path, config: dict) -> dict:
    # Path may itself be a symlink; check against the enclosing application folder.
    folder = path.parent
    manifest_path = contained(folder, "application.json", "application manifest")
    data = read_json(manifest_path)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise WorkspaceError(f"{path}: expected an object with schema_version: 1")
    if data.get("id") != folder.name:
        raise WorkspaceError(f"{path}: id must equal the application folder name")
    person = data.get("candidate")
    if not isinstance(person, dict) or person.get("name") != config["candidate"]["name"]:
        raise WorkspaceError(f"{path}: candidate does not match the selected workspace")
    if not isinstance(data.get("status"), str) or data["status"] not in APPLICATION_STATUSES:
        raise WorkspaceError(f"{path}: unknown application status")
    for field in ("company", "role"):
        if data["status"] == "unknown" and data.get(field) is None:
            continue
        nonempty(data.get(field), f"{path}: {field}")
    submission = data.get("submission")
    if not isinstance(submission, dict) or not isinstance(submission.get("status"), str) or submission["status"] not in SUBMISSION_STATUSES:
        raise WorkspaceError(f"{path}: unknown submission status")
    if data["status"] == "submitted" and submission["status"] != "submitted":
        raise WorkspaceError(f"{path}: submitted stage requires submission.status: submitted")
    if submission["status"] == "submitted":
        nonempty(submission.get("confirmation"), f"{path}: submission.confirmation")
        submitted_at = nonempty(submission.get("submitted_at"), f"{path}: submission.submitted_at")
        try:
            timestamp = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise WorkspaceError(f"{path}: submission.submitted_at must be an ISO timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise WorkspaceError(f"{path}: submission.submitted_at must include a time zone")
    files = data.get("files")
    if not isinstance(files, dict) or "jd" not in files:
        raise WorkspaceError(f"{path}: files must include jd")
    for key, value in files.items():
        target = contained(folder, value, f"{path}: files.{key}")
        if not target.is_file():
            raise WorkspaceError(f"{path}: files.{key} must point to a file")
    return data


def slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not text:
        raise WorkspaceError("Company and role need at least one letter or number")
    return text[:80].rstrip("-")


def init_workspace(args) -> None:
    name = nonempty(args.name, "candidate name").strip()
    target = Path(args.workspace).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise WorkspaceError(f"Refusing to overwrite an existing path: {target}")
    for filename in PROFILE_FILES:
        if not (PROFILE_ASSETS / filename).is_file():
            raise WorkspaceError(f"Missing packaged profile asset: {PROFILE_ASSETS / filename}")
    # mkdir is exclusive; an existing target is never reused, even when empty.
    target.mkdir(parents=True, exist_ok=False)
    profile = target / "profile"
    profile.mkdir()
    (target / "evidence").mkdir()
    (target / "applications").mkdir()
    for filename in PROFILE_FILES:
        shutil.copyfile(PROFILE_ASSETS / filename, profile / filename)
    write_json(profile / "sources.json", [])
    config = {
        "schema_version": 1,
        "candidate": {"name": name},
        "created_at": now(),
        "defaults": {"page_limit": 1},
        "profile": {
            "about": "profile/about.md",
            "skills_truth": "profile/skills_truth.md",
            "master_cv": "profile/master_cv.html",
            "style": "profile/style.css",
            "experiences": "profile/experiences.md",
            "review": "profile/review.md",
            "cv_style": "profile/cv_style.md",
        },
        "sources": "profile/sources.json",
        "applications": "applications",
    }
    write_json(target / "rolekit.json", config)
    print(f"Created workspace for {name}: {target}")
    print("Use onboard-candidate to build profile/ from a CV, notes, or a conversation; blank templates are not a completed profile.")


def new_application(args) -> None:
    root, config = workspace(args.workspace)
    # Validate the workspace before writing anything; reject imported external links too.
    load_sources(root, config)
    application_paths(root, config)
    company = nonempty(args.company, "company").strip()
    role = nonempty(args.role, "role").strip()
    source_url = args.url
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise WorkspaceError("--url must be an http:// or https:// posting URL")
    if args.jd:
        try:
            jd = Path(args.jd).expanduser().read_bytes()
            jd.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise WorkspaceError(f"Cannot read UTF-8 job description: {args.jd}: {exc}") from exc
        if not jd.strip():
            raise WorkspaceError("The supplied job description is empty")
    else:
        jd = ("# Job description\n\nPaste the full posting here before tailoring.\n").encode("utf-8")
    parent = contained(root, config["applications"], "applications")
    base = f"{slug(company)}_{slug(role)}"
    # Exclusive directory creation also avoids accidental reuse during concurrent runs.
    suffix = 1
    while True:
        identifier = base if suffix == 1 else f"{base}_{suffix}"
        folder = parent / identifier
        if folder.is_symlink():
            raise WorkspaceError(f"Refusing application path symlink: {folder}")
        try:
            folder.mkdir()
            break
        except FileExistsError:
            suffix += 1
    created = now()
    (folder / "jd.md").write_bytes(jd)
    data = {
        "schema_version": 1,
        "id": identifier,
        "candidate": {"name": config["candidate"]["name"]},
        "company": company,
        "role": role,
        "created_at": created,
        "source": {"url": source_url, "captured_at": created if args.jd else None},
        "status": "draft",
        "files": {"jd": "jd.md"},
        "submission": {"status": "not_started", "submitted_at": None, "confirmation": None},
    }
    write_json(folder / "application.json", data)
    print(f"Created draft: {folder}")
    if not args.jd:
        print("JD is a placeholder; capture the complete posting before tailoring.")


def browser_path() -> str | None:
    """Mirror render.discover_chrome without importing its PDF dependencies.

    Keep overrides, candidate order, and supported executable names aligned with
    render.py. An invalid explicit override prevents auto-discovery in both.
    """
    for variable in ("ROLEKIT_CHROME", "CHROME_BIN"):
        override = os.environ.get(variable)
        if override:
            value = os.path.expandvars(os.path.expanduser(override))
            found = shutil.which(value)
            return str(Path(found).resolve()) if found else None
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if os.environ.get(variable):
            base = Path(os.environ[variable])
            candidates.extend((base / "Google/Chrome/Application/chrome.exe", base / "Chromium/Application/chrome.exe"))
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "chrome.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return None


def doctor(args) -> None:
    root, config = workspace(args.workspace)
    sources = load_sources(root, config)
    paths = application_paths(root, config)
    for path in paths:
        load_application(path, root, config)
    print(f"Workspace OK: {root}")
    print(f"Candidate: {config['candidate']['name']}")
    print(f"Validated {len(sources)} evidence source(s) and {len(paths)} application manifest(s).")
    browser = browser_path()
    print(f"PDF browser (info): {browser or 'not found; install Chrome/Chromium or set CHROME_BIN'}")
    pypdf = importlib.util.find_spec("pypdf") is not None
    print(f"pypdf (info): {'available' if pypdf else 'not installed in this Python'}")
    print(f"uv (info): {shutil.which('uv') or 'not found; optional for render dependency setup'}")


def inspect_workspace(args) -> None:
    root, config = workspace(args.workspace)
    sources = load_sources(root, config)
    paths = application_paths(root, config)
    statuses: dict[str, int] = {}
    submissions: dict[str, int] = {}
    for path in paths:
        data = load_application(path, root, config)
        statuses[data["status"]] = statuses.get(data["status"], 0) + 1
        value = data["submission"]["status"]
        submissions[value] = submissions.get(value, 0) + 1
    result = {
        "workspace": str(root),
        "candidate": config["candidate"]["name"],
        "page_limit": config["defaults"]["page_limit"],
        "sources": len(sources),
        "applications": len(paths),
        "application_statuses": statuses,
        "submission_statuses": submissions,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"{result['candidate']} — {root}")
        print(f"Evidence sources: {len(sources)}; applications: {len(paths)}; page limit: {result['page_limit']}")
        print("Application status: " + (", ".join(f"{key}: {value}" for key, value in sorted(statuses.items())) or "none"))
        print("Submission status: " + (", ".join(f"{key}: {value}" for key, value in sorted(submissions.items())) or "none"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a new, separate candidate workspace")
    init.add_argument("workspace", help="New workspace directory; must not exist")
    init.add_argument("--name", required=True, help="Candidate's name")
    init.set_defaults(run=init_workspace)
    new = commands.add_parser("new", help="Create a distinct application draft without overwriting")
    new.add_argument("workspace", help="Explicit candidate workspace directory")
    new.add_argument("company")
    new.add_argument("role")
    new.add_argument("--url", help="Posting URL; this command does not fetch it")
    new.add_argument("--jd", metavar="PATH", help="Copy the full UTF-8 posting text exactly")
    new.set_defaults(run=new_application)
    check = commands.add_parser("doctor", help="Validate paths/manifests; report PDF readiness")
    check.add_argument("workspace")
    check.set_defaults(run=doctor)
    inspect = commands.add_parser("inspect", help="Summarize a selected candidate workspace")
    inspect.add_argument("workspace")
    inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    inspect.set_defaults(run=inspect_workspace)
    args = parser.parse_args(argv)
    try:
        args.run(args)
    except (WorkspaceError, OSError) as exc:
        print(f"rolekit: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
