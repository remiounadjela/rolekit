#!/usr/bin/env python3
"""Start a private candidate workspace from a CV, experience notes, or a conversation."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import uuid


# Installing a skill need not make its installation directory writable.
sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    if not path.is_file():
        raise SystemExit(f"Error: Missing packaged helper {path}. Install complete onboard-candidate and tailor-cv skill folders as siblings.")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


intake = _load("rolekit_start_intake", SCRIPTS / "import_input.py")
runtime = _load("rolekit_start_runtime", SCRIPTS.parents[1] / "tailor-cv/scripts/runtime.py")


def _workspace(args) -> tuple[Path, dict, bool]:
    if args.workspace:
        path = Path(args.workspace).expanduser().absolute()
        if path.exists() or path.is_symlink():
            root, config = intake.rolekit.workspace(path)
            intake.rolekit.load_sources(root, config)
            intake.rolekit.application_paths(root, config)
            if args.name and args.name.strip() != config["candidate"]["name"]:
                raise intake.rolekit.WorkspaceError("--name differs from the selected workspace's candidate; select the correct workspace or resolve its identity explicitly")
            return root, config, False
    else:
        path = runtime.data_dir() / "workspaces" / str(uuid.uuid4())
    with runtime._private_creation(), contextlib.redirect_stdout(io.StringIO()):
        intake.rolekit.init_workspace(SimpleNamespace(workspace=str(path), name=args.name or "New candidate"))
    root, config = intake.rolekit.workspace(path)
    return root, config, True


def _import(root: Path, source: Path, kind: str, python: Path) -> dict:
    command = [str(python), "-I", "-B", str(SCRIPTS / "import_input.py"), str(root), str(source), "--type", kind]
    try:
        completed = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        return {"input_type": kind, "original_filename": source.name, "status": "not_imported", "original_preserved": False, "diagnostic": str(exc)}
    try:
        imported = json.loads(completed.stdout)
        if not isinstance(imported, dict) or not imported.get("folder"):
            raise ValueError("unexpected importer result")
    except (ValueError, TypeError):
        return {"input_type": kind, "original_filename": source.name, "status": "not_imported", "original_preserved": False,
                "diagnostic": completed.stderr.strip() or completed.stdout.strip() or "Importer returned no result"}
    imported.update({"input_type": kind, "original_filename": source.name, "original_preserved": True,
                     "status": "imported" if completed.returncode == 0 else "needs_attention"})
    if completed.stderr.strip():
        imported["diagnostic"] = completed.stderr.strip()
    return imported


def start(args) -> dict:
    root, config, created = _workspace(args)
    inputs = []
    if args.cv:
        inputs.append(("cv", Path(args.cv).expanduser().absolute()))
    inputs.extend(("experience", Path(value).expanduser().absolute()) for value in args.experience)
    has_pdf = any(source.suffix.lower() == ".pdf" and source.is_file() for _, source in inputs)
    python = Path(sys.executable).absolute()
    dependency = {"status": "not_needed", "python": str(python), "managed": False}
    if has_pdf and args.skip_dependencies:
        dependency["status"] = "skipped"
        dependency["diagnostic"] = "Automatic package setup was skipped. Available host PDF packages will be used; otherwise originals are preserved for host-provided local extraction or OCR."
    elif has_pdf:
        try:
            python = runtime.ensure_pdf_python()
            dependency = {"status": "ready", "python": str(python), "managed": python != Path(sys.executable).absolute()}
        except runtime.RuntimeSetupError as exc:
            dependency = {"status": "failed", "python": str(python), "managed": False, "diagnostic": str(exc)}
            print(f"RoleKit: {exc}", file=sys.stderr)
    outcomes = [_import(root, source, kind, python if source.suffix.lower() == ".pdf" else Path(sys.executable).absolute())
                for kind, source in inputs]
    needs_name = config["candidate"]["name"] == "New candidate"
    missing = (["candidate_name"] if needs_name else []) + ([] if inputs else ["cv_or_experience_input"])
    failures = dependency["status"] == "failed" or any(item["status"] != "imported" for item in outcomes)
    review = any(item.get("extraction_status") in {"partial", "needs_review"} for item in outcomes)
    if failures:
        status = "needs_attention"
        next_action = "Review the diagnostics and preserved originals. Use available host-provided local extraction/OCR if package installation is unavailable; then organize the supported candidate material."
    elif not inputs:
        status = "awaiting_input"
        next_action = "Invite a CV upload or a conversational experience brain dump. A CV and candidate name are optional starting inputs."
    else:
        status = "needs_review" if review else "initialized"
        next_action = "Read the imported extracts, inspect available CV design, and build the reusable profile and sourced experience library. Ask conversationally about gaps."
    if needs_name:
        next_action += " Resolve the candidate name from an unambiguous supplied CV or ask in conversation; do not infer it from a filename."
    return {"workspace": str(root), "workspace_status": "created" if created else "resumed", "candidate": config["candidate"],
            "needs_candidate_name": needs_name, "setup_status": status, "profile_status": "not_assessed",
            "inputs": outcomes, "runtime": dependency, "missing": missing,
            "extraction_limits": list(dict.fromkeys(caveat for item in outcomes for caveat in item.get("caveats", []))),
            "next_action": next_action}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cv", help="Uploaded/local PDF, DOCX, Markdown, or text CV")
    parser.add_argument("--experience", action="append", default=[], help="Experience notes or speech-to-text transcript; repeat for multiple files")
    parser.add_argument("--name", help="Candidate name if already known; otherwise begin with a placeholder")
    parser.add_argument("--workspace", help="Explicit workspace to resume, or explicit new workspace location")
    parser.add_argument("--skip-dependencies", action="store_true", help="Use host extraction instead of installing optional packages")
    args = parser.parse_args(argv)
    try:
        output = start(args)
    except (intake.rolekit.WorkspaceError, runtime.RuntimeSetupError, OSError) as exc:
        print(json.dumps({"setup_status": "failed", "diagnostic": str(exc), "next_action": "Resolve the selected path or workspace configuration, then retry."}, indent=2))
        return 1
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 1 if output["setup_status"] == "needs_attention" else 0


if __name__ == "__main__":
    raise SystemExit(main())
