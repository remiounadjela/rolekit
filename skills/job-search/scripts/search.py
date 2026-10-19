#!/usr/bin/env python3
"""Local, candidate-scoped discovery and submission-attempt ledger.

This program performs no network requests or applications. A submitting/unknown
record is a retry lock, not evidence that an application reached its provider.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


STATES = ("discovered", "submitting", "submitted", "unknown", "blocked")
TRACKING_KEYS = {"gh_src", "referrer", "referral", "mc_cid", "mc_eid"}


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical_url(value):
    """Keep semantic parameters; collapse known ATS aliases and view suffixes."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("url must be a nonempty http(s) URL")
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("url must be an absolute http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs must not contain credentials")
    host = parsed.hostname.lower()
    port = parsed.port
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port in (None, 443 if parsed.scheme.lower() == "https" else 80) else f"{host}:{port}"
    scheme = parsed.scheme.lower()
    path = parsed.path or "/"
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS]
    fragment = parsed.fragment
    if host == "jobs.ashbyhq.com":
        scheme = "https"
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[-1].lower() in ("application", "overview"):
            parts.pop()
        path = "/" + "/".join(parts)
        # Ashby UUID routes are case insensitive; organization slugs are not assumed so.
        if len(parts) == 2 and len(parts[1]) == 36:
            path = f"/{parts[0]}/{parts[1].lower()}"
        query = [(key, val) for key, val in query if key.lower() not in ("source", "ref")]
        fragment = ""
    elif host in ("boards.greenhouse.io", "job-boards.greenhouse.io",
                  "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io"):
        scheme = "https"
        netloc = "job-boards.eu.greenhouse.io" if ".eu." in host else "job-boards.greenhouse.io"
        params = dict(query)
        if path.rstrip("/") in ("/embed/job_app", "/embed/job_board") and params.get("for") and params.get("token"):
            path = f"/{params['for']}/jobs/{params['token']}"
            query = [(key, val) for key, val in query if key not in ("for", "token")]
        else:
            path = path.rstrip("/") or "/"
        query = [(key, val) for key, val in query if key.lower() not in ("source", "ref")]
        fragment = ""
    # Stable ordering removes differences from link builders, retaining repeated values.
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), fragment))


def job_key(url):
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:24]


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON {path}: {exc}") from exc


def contained(root, value, *, file=False):
    root = Path(root).resolve()
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("Expected a workspace-contained path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path must remain inside selected workspace: {value}")
    if file and not path.is_file():
        raise ValueError(f"Evidence/artifact must be an existing file: {value}")
    return path


def proof(root, value):
    root = Path(root).resolve()
    path = contained(root, value, file=True)
    return {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validated_item(item):
    if not isinstance(item, dict):
        raise ValueError("Each discovery item must be an object")
    for key in ("company", "title", "url"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError(f"Discovery item requires nonempty {key}")
    canonical = canonical_url(item["url"])
    if item.get("source_url") is not None:
        canonical_url(item["source_url"])
    ats_id = item.get("ats_id")
    if ats_id is not None and (not isinstance(ats_id, str) or not ats_id.strip()):
        raise ValueError("ats_id must be a nonempty string when supplied")
    return {"job_key": job_key(canonical), "canonical_url": canonical,
            "url": item["url"].strip(), "company": item["company"].strip(),
            "title": item["title"].strip(), "source_url": item.get("source_url"), "ats_id": ats_id}


def insert_job(db, item):
    stamp = now()
    result = db.execute("""INSERT OR IGNORE INTO jobs
        (job_key, canonical_url, url, company, title, source_url, ats_id, status, first_seen, last_seen)
        VALUES (:job_key, :canonical_url, :url, :company, :title, :source_url, :ats_id,
                'discovered', :stamp, :stamp)""", {**item, "stamp": stamp})
    db.execute("UPDATE jobs SET last_seen=? WHERE job_key=?", (stamp, item["job_key"]))
    return bool(result.rowcount)


def bootstrap(db, root, config):
    """Import explicit legacy URL/status evidence before allowing any attempt."""
    directory = contained(root, config.get("applications", "applications"))
    count = 0
    if not directory.exists():
        return count
    for manifest in sorted(directory.glob("*/application.json")):
        manifest = contained(root, manifest, file=True)
        data = read_json(manifest)
        if not isinstance(data, dict):
            raise ValueError(f"Application manifest must be an object: {manifest}")
        candidate = data.get("candidate")
        if candidate is not None and candidate != config.get("candidate"):
            raise ValueError(f"Application candidate differs from selected workspace: {manifest}")
        source = data.get("source") or {}
        submission = data.get("submission") or {}
        if not isinstance(source, dict) or not isinstance(submission, dict):
            raise ValueError(f"Invalid application source/submission: {manifest}")
        url = source.get("url")
        status = submission.get("status")
        if not url or status not in ("submitted", "unknown"):
            continue
        item = validated_item({"company": data.get("company") or "Unknown company",
                               "title": data.get("role") or "Unknown role", "url": url})
        manifest_proof = proof(root, manifest)
        previous = db.execute("SELECT sha256 FROM bootstrap_sources WHERE path=?",
                              (manifest_proof["path"],)).fetchone()
        if previous and previous[0] == manifest_proof["sha256"]:
            continue
        insert_job(db, item)
        current = db.execute("SELECT status FROM jobs WHERE job_key=?", (item["job_key"],)).fetchone()[0]
        # An old manifest cannot downgrade confirmed completion or unlock an attempt.
        if current != "submitted" and (current != "unknown" or status == "submitted"):
            db.execute("UPDATE jobs SET status=? WHERE job_key=?", (status, item["job_key"]))
            pending = db.execute("SELECT id FROM attempts WHERE job_key=? AND status='submitting'",
                                 (item["job_key"],)).fetchone()
            if pending:
                attempt_id = pending[0]
                db.execute("UPDATE attempts SET status=?, resolved_at=?, evidence_json=? WHERE id=?",
                           (status, now(), json.dumps(manifest_proof), attempt_id))
            else:
                result = db.execute("""INSERT INTO attempts
                    (job_key, started_at, resolved_at, status, artifacts_json, evidence_json, origin)
                    VALUES (?, ?, ?, ?, '[]', ?, 'legacy')""",
                    (item["job_key"], now(), now(), status, json.dumps(manifest_proof)))
                attempt_id = result.lastrowid
            db.execute("INSERT INTO outcomes (attempt_id, recorded_at, status, evidence_json) VALUES (?, ?, ?, ?)",
                       (attempt_id, now(), status, json.dumps(manifest_proof)))
        db.execute("INSERT OR REPLACE INTO bootstrap_sources (path, sha256, job_key) VALUES (?, ?, ?)",
                   (manifest_proof["path"], manifest_proof["sha256"], item["job_key"]))
        count += 1
    return count


@contextmanager
def ledger(workspace):
    root = Path(workspace).expanduser().resolve()
    manifest = contained(root, "rolekit.json", file=True)
    config = read_json(manifest)
    if not isinstance(config, dict) or not isinstance(config.get("candidate"), dict) or not config["candidate"].get("name"):
        raise ValueError("rolekit.json must identify the selected candidate")
    directory = contained(root, "search")
    directory.mkdir(exist_ok=True)
    database = contained(root, directory / "ledger.sqlite3")
    db = sqlite3.connect(database, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for key, value in (("workspace", str(root)), ("candidate", json.dumps(config["candidate"], sort_keys=True))):
            previous = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            if previous and previous[0] != value:
                raise ValueError("Ledger belongs to another workspace/candidate; do not reuse its database")
            db.execute("INSERT OR IGNORE INTO metadata VALUES (?, ?)", (key, value))
        db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            job_key TEXT PRIMARY KEY, canonical_url TEXT NOT NULL UNIQUE, url TEXT NOT NULL,
            company TEXT NOT NULL, title TEXT NOT NULL, source_url TEXT, ats_id TEXT,
            status TEXT NOT NULL CHECK(status IN ('discovered','submitting','submitted','unknown','blocked')),
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY, job_key TEXT NOT NULL REFERENCES jobs(job_key),
            started_at TEXT NOT NULL, resolved_at TEXT, status TEXT NOT NULL,
            artifacts_json TEXT NOT NULL, evidence_json TEXT, origin TEXT NOT NULL)""")
        db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_submitting_attempt
            ON attempts(job_key) WHERE status='submitting'""")
        db.execute("""CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL REFERENCES attempts(id),
            recorded_at TEXT NOT NULL, status TEXT NOT NULL, evidence_json TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS bootstrap_sources (
            path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, job_key TEXT NOT NULL REFERENCES jobs(job_key))""")
        imported = bootstrap(db, root, config)
        yield db, root, imported
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def get_job(db, key):
    row = db.execute("SELECT * FROM jobs WHERE job_key=?", (key,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown job_key: {key}; ingest the job first")
    result = dict(row)
    result["attempts"] = []
    for attempt in db.execute("SELECT * FROM attempts WHERE job_key=? ORDER BY id", (key,)):
        entry = dict(attempt)
        entry["artifacts"] = json.loads(entry.pop("artifacts_json"))
        entry["evidence"] = json.loads(entry.pop("evidence_json") or "null")
        entry["outcomes"] = [{"recorded_at": row[0], "status": row[1], "evidence": json.loads(row[2])}
                             for row in db.execute("SELECT recorded_at, status, evidence_json FROM outcomes WHERE attempt_id=? ORDER BY id",
                                                   (entry["id"],))]
        result["attempts"].append(entry)
    return result


def execute(args):
    items = None
    if args.command == "ingest":
        raw = read_json(Path(args.items).expanduser())
        if not isinstance(raw, list):
            raise ValueError("--items must contain a JSON list")
        items = [validated_item(item) for item in raw]
    with ledger(args.workspace) as (db, root, imported):
        if args.command == "ingest":
            inserted = sum(insert_job(db, item) for item in items)
            keys = list(dict.fromkeys(item["job_key"] for item in items))
            return {"inserted": inserted, "existing": len(items) - inserted, "bootstrapped": imported,
                    "jobs": [get_job(db, key) for key in keys]}
        if args.command == "list":
            return [get_job(db, row[0]) for row in db.execute("SELECT job_key FROM jobs ORDER BY first_seen, job_key")]
        job = get_job(db, args.job_key)
        if args.command == "begin-attempt":
            if job["status"] not in ("discovered", "blocked"):
                raise ValueError(f"Cannot begin: job is {job['status']}. Never retry an uncertain or completed submission.")
            artifacts = [proof(root, item) for item in args.artifact]
            db.execute("UPDATE jobs SET status='submitting' WHERE job_key=?", (args.job_key,))
            db.execute("""INSERT INTO attempts (job_key, started_at, status, artifacts_json, origin)
                VALUES (?, ?, 'submitting', ?, 'local')""", (args.job_key, now(), json.dumps(artifacts)))
        elif args.command == "resolve-attempt":
            if args.status == "blocked" and not args.pre_submit:
                raise ValueError("blocked requires --pre-submit: assert no submission action occurred; post-click uncertainty is unknown")
            if args.pre_submit and args.status != "blocked":
                raise ValueError("--pre-submit is only valid with --status blocked")
            if job["status"] != "submitting" and not (job["status"] == "unknown" and args.status == "submitted"):
                raise ValueError(f"Cannot resolve job in {job['status']} state")
            evidence = proof(root, args.evidence)
            attempt = db.execute("SELECT id FROM attempts WHERE job_key=? ORDER BY id DESC LIMIT 1", (args.job_key,)).fetchone()
            db.execute("UPDATE attempts SET status=?, resolved_at=?, evidence_json=? WHERE id=?",
                       (args.status, now(), json.dumps(evidence), attempt[0]))
            db.execute("INSERT INTO outcomes (attempt_id, recorded_at, status, evidence_json) VALUES (?, ?, ?, ?)",
                       (attempt[0], now(), args.status, json.dumps(evidence)))
            db.execute("UPDATE jobs SET status=? WHERE job_key=?", (args.status, args.job_key))
        return get_job(db, args.job_key)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Deduplicate discovery items from a JSON file")
    ingest.add_argument("workspace")
    ingest.add_argument("--items", required=True, help="JSON file, independent from the selected workspace")
    listing = commands.add_parser("list", help="List jobs and recorded attempts")
    listing.add_argument("workspace")
    begin = commands.add_parser("begin-attempt", help="Lock a job before any provider submission action")
    begin.add_argument("workspace")
    begin.add_argument("job_key")
    begin.add_argument("--artifact", action="append", default=[], help="Existing file relative to workspace, repeatable")
    resolve = commands.add_parser("resolve-attempt", help="Record outcome evidence; never infer success from a timeout")
    resolve.add_argument("workspace")
    resolve.add_argument("job_key")
    resolve.add_argument("--status", choices=("submitted", "unknown", "blocked"), required=True)
    resolve.add_argument("--evidence", required=True, help="Existing evidence file relative to workspace")
    resolve.add_argument("--pre-submit", action="store_true", help="Assert no submission action occurred (blocked only)")
    try:
        result = execute(parser.parse_args(argv))
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
