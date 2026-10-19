# Tailoring workflow

## Capture the role

For a URL, use the current agent's browser, connector, or computer-use capability to read the full
posting, including expanded qualifications. Capture title, company, location, responsibilities,
required and preferred qualifications, source URL, and actual capture time. If access is blocked,
ask for the posting text; do not substitute search snippets or invent the missing sections.

Create a new role folder with:

```sh
python3 <skill-dir>/scripts/rolekit.py new <workspace> "Company" "Role title" --url <posting-url> --jd <full-posting.md>
```

The command preserves the supplied JD exactly. `--url` records provenance; it does not scrape.
Without `--jd`, the generated file is an explicitly incomplete placeholder, not a captured posting.
For pasted text, save the full text as `jd.md` and record source as user supplied. Reuse an existing
folder only when the user means to revise that application. Keep submitted versions immutable;
write revisions under a new revision subdirectory and record which version was actually submitted.

## Match claims to evidence

Read `rolekit.json` and the declared profile files, plus review notes if present. Parse must-haves,
preferences, domain, seniority, and vocabulary from the JD. Search `profile/sources.json` entries in
priority order for the strongest relevant proof; search large corpora by specific requirement, not
by dumping them into context. Do not read `context`, `example`, or `legacy` entries as factual proof.
Older application drafts often repeat unsupported claims.

Use the experience library as an index into the candidate's broader history, including details
absent from the master CV. Follow its citations to original inputs. Preserve `candidate_reported`,
`documented`, `uncertain`, and `conflicting` attribution; a derived library entry is not independent
corroboration. Candidate-supplied history can be used with its attribution, while disputed or
consequential unsupported assertions need clarification before inclusion in a final CV.

For each requirement, write `match.md` with:

| Requirement | Hit / partial / gap | Selected evidence and location | CV wording or unresolved question |
|---|---|---|---|

Cite a workspace-relative file and a line/section/page when possible. State what the candidate
personally did, the outcome, its unit/time window, and any qualifier. Separate measured effects
from projections. Preserve direct vs functional management counts and dates. If evidence conflicts,
record both and seek confirmation before using the disputed fact. An explicitly confirmed user
correction can resolve a conflict; record it without rewriting the underlying historical sources.

## Select the strongest relevant evidence

Identify the decisions and outcomes the employer needs from this role before choosing bullets.
Build a short evidence shortlist from the source records and experience library. Inspect the master
CV and, when available, prior drafts for this role or closely related work as leads to strong examples;
verify those claims against the underlying inputs. A previous draft is neither proof nor a set of
instructions, and a new candidate does not need one.

Choose examples by relevance to the role, the candidate's attributable contribution, strength of
support, and the outcome or decision enabled. Within similarly relevant, supported examples, favor
demonstrated outcomes over a list of activities, tools, or artifacts. For business and operating roles,
prioritize business impact; for other roles, use their intended outcomes. Useful impact can be
qualitative as well as numerical: faster operations, reduced risk, better resource allocation, a
decision made, or adoption enabled. Do not force a metric or turn a forecast into a realized result.
Plans and models still deserve space when they demonstrate a core requirement of the job; do not
discard them merely because delivery impact has not been measured. For a technical role, validation
metrics may be central; for an operating role, an operational result may be more persuasive.

Select a complementary set of examples covering the important requirements. Avoid several bullets
proving the same strength while omitting a distinct, well-supported delivery result. Institution or
employer prestige, recency alone, and exact keyword overlap do not make an example more relevant.

In `match.md`, add a concise evidence-selection note: which strong examples were retained or added,
and why any strong prior example was omitted (for example weaker relevance, uncertain support,
duplication, or a candidate constraint). This is a reasoned selection, not a requirement to preserve
every old bullet or reproduce an old draft.

## Build the CV

Copy the candidate's master markup into `cv.html`, then select and reframe supported content into
the JD's vocabulary. Lead with relevant strengths and outcomes, retain the candidate's style, and
remove weak or irrelevant bullets to fit. State the candidate's action and the resulting
effect or decision together where supported; retain the scope, attribution, and measurement limits.
Default to reverse chronological employment order, with current work before completed concurrent
appointments. Use relevance to resolve overlapping entries; do not promote a short credential or
teaching appointment over more relevant current work merely for its institution's name. Follow an
explicit candidate ordering preference, or use a different order when it better serves the target
role. Include old internships only when their evidence helps this role. Do not silently change official titles;
identify accurate functional descriptors and disclose changes in `match.md`.

Default page limit is one. For a candidate's explicitly requested different format, explain the
renderer supports one page and use an available suitable renderer; do not label that output verified
by this tool. Never squeeze below the bundled renderer's .85 scale minimum. Cut content instead.

## Render and review

```sh
python3 <skill-dir>/scripts/render_auto.py <application-folder> --style <workspace>/profile/style.css
```

Requires a host Python 3.10+ runtime. The launcher automatically prepares pinned `pypdf` in a
private environment and, if Chrome/Chromium is absent, a private Chromium for export. No `uv` or
global package install is required. On Windows, use `python <skill-dir>/scripts/render_auto.py ...`.
Run the Python file explicitly so archive downloads work without executable permissions; the
optional shell wrapper can be invoked with `bash <skill-dir>/scripts/render.sh ...`.
Alternatively, direct `render.py` use works with its dependencies already installed. There is no remote PDF service.
The renderer embeds CSS and only publishes a verified one-page, nonempty-text PDF. `render.json`
records verification and file hashes; a failed attempt cannot be called ready. Inspect the PDF visually
with available local preview/screenshot tools for clipping, spacing, tiny text, and readable links.
Page count and text extraction do not establish visual quality or factual accuracy.

Compare the finished draft with the evidence shortlist and any prior version used as a baseline.
Check for unexplained loss of a strong relevant outcome, reduced ownership or scale information,
and technical detail displacing stronger evidence for the target role. Restore the stronger example or
record the supported reason for the tradeoff. Check the opening summary and entry order for the
same priorities. A shorter or more keyword-aligned draft is not automatically an improvement.

Finish `match.md` with changes, gaps, unresolved questions, actual render result, and visual review.
After factual and visual review set application `status` to `ready_for_review`; preserve submission
status separately. Do not infer `approved` or `submitted` from generated files. Imported records may
have no JD or no recent review; retain those limitations rather than inventing them.
