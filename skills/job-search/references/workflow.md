# Search and application workflow

## Candidate setup

Select one workspace using `rolekit.json`. If no usable candidate profile exists yet, use the sibling
`onboard-candidate` skill when installed, or `tailor-cv`'s workspace setup instructions. Read the
declared profile, experience library, evidence map, and review notes (default `profile/review.md`)
before relying on candidate history. Keep the following files private:

- `search/config.json`: copy [assets/config.json](../assets/config.json) and configure the selected
  sources, brief path, application-facts path, mode, daily cap, and authorization.
- `profile/search_brief.md`: copy [assets/brief.md](../assets/brief.md). Separate confirmed facts,
  current preferences, provisional hypotheses, and unanswered questions. Record provenance and dates
  for consequential criteria. An aspiration is not experience evidence.
- `profile/application_facts.md`: candidate-supplied contact details, work eligibility, recurring
  factual answers, and any optional disclosure choices they actually supplied. Include each answer's
  scope and source/date; a prior answer for one employer is not a universal willingness or consent.

`sources` entries have `id`, `url`, `type` (`webpage` or `rss`), and `enabled`. The default mode is
`prepare`; `authorization` starts null. `daily_limit` caps new application preparations/submissions
per candidate per day, not discoveries or a quota to fill. Resuming a role does not create a new
allowance, and a prepared application later submitted is counted once for that day. The host task
sets the daily cadence and candidate timezone. Record source scan times and failures in private
`search/runs/` records; avoid another same-day scan unless explicitly requested or retrying a failed
source. Do not assume a failed or inaccessible scan means no new jobs. The agent enforces the
configured mode, scope, cadence, and cap from these records; ledger helpers do not decide that policy.
When an edition is unchanged, still inspect the run records for unreviewed postings or unfinished
authorized work. An unchanged source does not clear the existing queue.

An authorization record must preserve the user's actual instruction and its date/source, selected
candidate, allowed actions, and scope. Scope can be concrete named roles or a bounded selection
policy with an approved criteria snapshot, source boundaries, limits, and duration. Identify the
authorized inbox if email verification is included. Do not widen it when criteria change. A broad
goal to find work, an enabled config flag, or permission to prepare CVs is insufficient to submit.
Use the host's permission rules if they require a narrower or action-time approval.

## Scan and preserve identity

Read the enabled newsletter, feed, or job-board sources with the host's available browser/connectors.
Follow relevant entries to original employer/ATS postings. Keep source provenance separate from the
employer URL. Read the full posting and verify it is open before choosing it; search snippets or an
aggregator's role label cannot substitute for the JD. If the source lists only titles, discover the
details before deciding fit. Respect access restrictions and report inaccessible sources.

Use the bundled ledger helper, with paths resolved relative to this skill:

```sh
python3 <skill-dir>/scripts/search.py ingest <workspace> --items <workspace>/search/run-items.json
python3 <skill-dir>/scripts/search.py list <workspace>
```

`--items` is a UTF-8 JSON file containing an array, for example:

```json
[
  {
    "company": "Example Company",
    "title": "Example role",
    "url": "https://employer.example/careers/role-123",
    "source_url": "https://source.example/jobs",
    "ats_id": "role-123"
  }
]
```

`company`, `title`, and `url` are required; `source_url` and `ats_id` are optional. Preserve employer
posting IDs when available. `ingest` reports inserted/existing counts and `jobs`; use the returned
`job_key`, never fabricate one from a title. State is private in `search/ledger.sqlite3`.

The ledger protects posting identity and submission attempts. It does not fetch pages, choose fit,
render CVs, operate the browser, or grant authorization. Existing application manifests with posting
URLs are bootstrapped conservatively. Also inspect likely matching legacy company/role folders:
older records without usable URLs may need manual identity reconciliation. Do not treat missing
confirmation as proof that an imported application was never sent.

## Screen and prepare

Record each decision under `search/reviews/<job_key>.md`, using workspace-relative evidence links.
Include the original posting URL, live-check time, candidate brief version/date, strongest matches,
material gaps, uncertainty, and a reason for `shortlist`, `review`, or `skip`.

First check stated hard constraints: location, office requirements, eligibility, compensation when
published, and other candidate-confirmed exclusions. Unknown candidate facts remain questions;
unknown employer facts remain uncertainty. A mismatch is not fixed by tailoring the CV.

Then compare the work with what the candidate wants to do and can demonstrate. Consider scope,
seniority, actual responsibilities, outcomes, customer/technical context, and supported strengths.
Distinguish a role that performs the desired work from a generic role at a company in that industry.
Explain adjacent opportunities as such; do not let title keywords substitute for this assessment.

For a shortlisted role, read the sibling `tailor-cv/SKILL.md` and use its existing helpers and evidence
guardrails. Check the ledger and prior folders before calling `rolekit.py new`. Link the returned
application folder in the review record, and keep using it on later runs. Preserve the original JD,
`match.md`, `cv.html`, verified `cv.pdf`/`render.json`, and proposed answers. Keep submitted versions
immutable. Neither a high fit assessment nor a valid PDF proves candidate approval.

Prepare `answers.md` using the live form's question text, exact proposed answer, source, and unresolved
questions. Ask only for consequential missing inputs and continue independent preparation meanwhile.
Optional sensitive disclosures remain optional. Do not invent eligibility, current salary, employer
commitments, willingness to relocate, or demographic answers from indirect evidence.

## Execute an authorized application

Recheck that the role is open, the identity matches the existing record, authorization is valid, the
candidate/materials are correct, and consequential answers are resolved. `prepare` mode ends at
reviewable artifacts. A later explicit instruction may authorize a concrete batch or a bounded policy;
record it before changing mode or executing external actions.

Before uploading/submitting, create an attempt with the final CV and answer record:

```sh
python3 <skill-dir>/scripts/search.py begin-attempt <workspace> <job_key> --artifact <workspace>/applications/<role>/cv.pdf --artifact <workspace>/applications/<role>/answers.md
```

The helper records artifact paths and hashes. Also preserve the final URL, authorization scope,
answers, and actual submitted version in the role's `submission.md`. If materials must change after
the attempt begins, first establish that no submit action occurred. Resolve that known pre-submit
attempt as blocked, record the change, and create a new attempt with the corrected artifacts before
proceeding. If a submit action may have occurred, preserve the uncertain outcome instead.

Use authorized host browser/computer-use tools. For ordinary email verification, use only the
authorized candidate inbox and the expected sender/application/time window. Use the code or link
transiently, check the destination, and retain only the necessary confirmation evidence. Do not save
OTP values, login cookies, passwords, or authentication exports. Stop for access-control challenges
according to host policy, new consequential facts, payments, contracts, or account actions outside
the authorization. Avoid redundant approval questions for already-authorized screens.

After submitting, inspect the confirmation screen, application portal, and/or confirmation email.
Save a workspace-contained receipt or factual evidence file, then resolve the attempt:

```sh
python3 <skill-dir>/scripts/search.py resolve-attempt <workspace> <job_key> --status submitted --evidence <workspace>/applications/<role>/receipt.md
```

Update the role's `application.json` and `submission.md` consistently with the verified result,
timestamp, receipt, exact artifacts, and answers. A button click or complete form is not proof.

If the click times out, the process crashes, or the outcome is unclear, preserve what happened and
resolve to `unknown` with an evidence file. `submitted`, `submitting`, and `unknown` prevent another
begin attempt. Inspect receipt/email/portal evidence first; an unknown outcome can later be resolved
to `submitted` with its receipt without clicking submit again. Otherwise leave it unresolved.

Use `blocked --pre-submit` only when evidence establishes a blocker occurred before any submission:

```sh
python3 <skill-dir>/scripts/search.py resolve-attempt <workspace> <job_key> --status blocked --pre-submit --evidence <workspace>/applications/<role>/blocker.md
```

This status permits a later retry after fixing the known pre-submit issue. Never classify an
ambiguous click as pre-submit merely to unlock retry. Every resolution needs an existing evidence
file; its hash is recorded. An already submitted role does not become eligible again because the
source repeats it, its wording changes, the next daily run starts, or a new CV exists.

## Scheduled runs and reporting

A host-specific recurring task may invoke this workflow with the selected candidate/config, browser,
and authorized inbox. Creating a skill or config does not activate that task. Establish schedule and
execution authorization explicitly using the host's scheduling tools; do not add cron or a background
sender as a workaround. No model API key is required by these helpers.

Persist each run's scan timestamps, source failures, discovered/existing counts, decision links,
prepared/submitted/unknown/blocked results, and any needed input. Stay quiet on scheduled runs with
no meaningful change; notify about useful new roles, completion, failure, or required action. In the
final report use concrete status counts and distinguish preparation, verified submission, and hiring
outcomes. Do not report a skipped or inaccessible source as successfully checked.
