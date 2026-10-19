# Verification

The initial extraction passed 38 tests covering workspace, renderer, and migration behavior, plus a real local Chrome
render of an imported CV, and an independent synthetic candidate workflow. The skill frontmatter
also passes the skill-creator validator.

The renderer tests cover one-page fitting, nonempty PDF text, final artifact hashes, repeated
rendering, oversized-document failure preservation, and browser timeouts. The workspace tests
cover separate people, exact JD preservation, collision-safe folders, no-clobber creation, portable
source paths, and distinct unknown/prepared/submitted states.

The original repository is checked by comparing its full Git status and SHA-256 hashes for each
imported file. The private migration manifest also verifies the standalone copies. Those checks
and the actual counts live in the candidate workspace's migration/ directory.

Runtime rendering was exercised on macOS. Chrome/Chromium discovery includes Windows and Linux,
but those platforms have not been exercised here. A PDF page-count/text check is complemented by
visual inspection and does not prove factual accuracy or provider submission.

## Job-search extension

The combined suite passes 53 tests, including 15 new ledger tests. These cover ATS URL aliases,
repeat discovery, semantic URL parameters, candidate/workspace isolation, contained artifact and
evidence hashes, concurrent attempt locking, legacy history, unknown-outcome retry protection,
and retaining uncertainty evidence when later receipts confirm a submission.

Both skill entrypoints pass the skill-creator validator. The active private workspace passes its
doctor check. The two-skill share bundle was inspected to exclude candidate workspaces and caches.

An independent agent exercised the search skill against an isolated offline candidate and four
complete JD fixtures. It selected the relevant AI-advisory role, rejected an AI employer's revenue-
operations role, preserved an existing submitted application and an unknown outcome, and recorded
decisions for later resumption. It made no CVs or external actions because that test request excluded
them. Live source access, fit judgment, and recurring execution remain host-agent capabilities;
local ledger tests do not establish that an unattended browser application will succeed.

A separate live newsletter pilot captured 42 posting links and reviewed six new employer JDs.
Repeating its ingest created zero duplicate records. Its detailed coverage and decisions are private
candidate records. No new applications were submitted by that pilot. A scheduled unattended run
has not been exercised as part of this verification.

## Candidate onboarding extension

The combined suite passes 77 tests, including 21 input-import tests and three additional workspace
checks. Input coverage includes UTF-8 text/Markdown, DOCX paragraphs/tables/headers/text boxes,
page-labelled PDF text, image-only pages, malformed documents and encodings, optional dependencies,
exact original bytes and hashes, collision-safe imports, candidate isolation, profile immutability,
and execution after copying the sibling skills outside this repository. Existing workspaces without
the new optional profile keys continue to validate. All three skill entrypoints pass quick validation.

An independent agent completed two offline onboarding scenarios in isolated synthetic workspaces:
DOCX plus dictated notes, and a first CV from conversation only. Both produced a master CV, a separate
source-linked experience library, claim guardrails, design limitations, and open questions; both
passed `doctor`. The first scenario preserved a corrected scope claim and distinguished a target
from a measured outcome. The second used volunteering and education without inventing employment.
Neither needed a target posting or answers to optional questions to produce a usable baseline.

Both resulting baselines rendered with real local Chrome at scale 1.00 as one-page PDFs with
extractable text and artifact hashes. Page images were inspected for readable text, clipping, and
spacing. The DOCX's original design was not visually inspected, so the neutral template was used
and that approximation was recorded. Actual audio transcription, OCR, native Word design fidelity,
and Windows/Linux execution were not exercised by these onboarding tests.

## Automatic setup extension

The complete suite passes 103 tests. The additional 17 setup/runtime and nine render-setup tests
cover nameless fresh starts, private UUID workspaces, transcript additions into the same workspace,
explicit resume, copied installations and unrelated working directories, exact dependency versions,
private venv reuse, offline failure preservation, browser setup, old verification invalidation, and
isolated subprocesses that cannot import a same-named package from the caller's directory.

A real cold start used a plain Python without `pypdf` and supplied only an uploaded PDF: the launcher
created a fresh private workspace, provisioned a local venv, installed the pinned reader, and
preserved/extracted the CV without a name, workspace path, `uv`, or global package installation.
An independent agent then used only copied installed skill folders, an uploaded PDF, and dictated
notes to create a usable source-linked profile without technical or optional user questions. It
derived the candidate name from CV content and added notes into the returned workspace. Original
hashes, source links, installed-skill immutability, and `doctor` were checked.

PDF export passed through the automatic shell wrapper using an installed Chrome and private reader.
The missing-browser path was also exercised with discovery reporting no installed Chrome: pinned
Playwright and a real private Chromium headless shell were downloaded, and the unchanged offline
renderer produced a verified one-page PDF. A fresh shell-only browser download was exercised too.
Both resulting PDFs were visually inspected. Only package/browser binaries were downloaded; no
candidate document was uploaded to a conversion service. macOS was exercised live; Windows/Linux
paths and setup behavior have automated coverage but no live platform smoke.

## GitHub installation

The public repository was installed into a fresh temporary destination using Codex's GitHub skill
installer with all three skill paths. Downloaded archives omit executable permissions, so canonical
startup and rendering instructions explicitly invoke Python. The setup regression also removes all
file executable bits before exercising the installed layout. A real downloaded installation created
a fresh private workspace, preserved both a CV and experience transcript, and passed `doctor`
without modifying the skill installation or global configuration.
