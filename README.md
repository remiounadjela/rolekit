# RoleKit

**Start with your CV or your story. Build a CV for each role.**

RoleKit gives your agent three reusable skills:

1. **`onboard-candidate`** turns an existing CV and/or an experience brain dump into a private
   profile, an editable CV template, and a reusable experience library. Start without a CV if needed.
2. **`tailor-cv`** matches that history to a specific posting and produces a reviewed one-page PDF
   with a hit/partial/gap assessment.
3. **`job-search`** scans your selected sources, assesses fit, and coordinates tailoring and
   specifically authorized applications.

Candidate facts stay in their own workspace. No model API key, server, or model-specific browser
plugin is required by the local helpers. The host agent supplies conversation, document inspection,
browser access, and any speech transcription or scheduling capabilities.

## Start with your agent

In Codex, paste this installation request:

Install the three RoleKit skills from https://github.com/remiounadjela/rolekit: `skills/onboard-candidate`,
`skills/tailor-cv`, and `skills/job-search`. Install all three as sibling skill folders.

After installation, upload your CV in a new message and say:

> Use onboard-candidate. Here's my CV. I'll tell you about experiences missing from it.

Or start from nothing:

> Use onboard-candidate. I don't have a CV yet. Help me talk through my experience and build one.

Setup is automatic: the agent creates your private workspace, imports the CV, and prepares missing
document dependencies. You do not need to choose directories, install packages, or run commands.
Your name can come from the CV or conversation; you can start without supplying it separately.

You can provide either input, both, or add more later. A speech-to-text transcript works as text;
audio itself needs a transcription tool in your agent. The agent preserves originals, organizes
your history, and asks about consequential missing details. You do not need to prepare Markdown,
edit configuration, or assemble a company knowledge base. Text extraction recovers content;
recreating a CV's design also needs visual inspection and may be approximate.

Once your profile is usable:

> Tailor my CV for this posting: [URL].

In the same chat, the agent already knows your workspace. For a new person, it creates a separate
one; it never chooses a global active candidate or reuses a profile just because a name matches.

For another person, start onboarding with their own inputs. The reusable skills contain
no candidate facts. Local adapters support Claude Code and Codex; another agent can read the same
Markdown entrypoints directly.

For another agent, install the complete skill folders as described under
[Use the skill elsewhere](#use-the-skill-elsewhere). GitHub distributes the reusable tools; personal
profiles stay on the candidate's computer. When moving computers, back up and transfer the private
workspace separately from reinstalling the skills.

## Local commands (optional, for agents and developers)

Python 3.10+ is enough to manage workspaces:

```sh
skills/onboard-candidate/scripts/start.sh --cv /path/to/cv.pdf
# The result returns the private workspace path for follow-up inputs.
# On Windows: python skills/onboard-candidate/scripts/start.py --cv C:\path\to\cv.pdf
# Lower-level manual setup remains available:
./rolekit init workspaces/my-profile --name "Your Name"
# Have your agent run onboard-candidate, or populate profile/ and sources yourself.
# Optional local input preservation/extraction:
python3 skills/onboard-candidate/scripts/import_input.py workspaces/my-profile /path/to/cv.docx --type cv
python3 skills/onboard-candidate/scripts/import_input.py workspaces/my-profile /path/to/notes.md --type experience
# Once the profile is usable:
./rolekit new workspaces/my-profile "Company" "Role title" --jd /path/to/posting.md --url https://example.com/job
./rolekit inspect workspaces/my-profile
./rolekit doctor workspaces/my-profile
```

`new` records a URL but does not scrape it. Your agent reads the full posting with its available
browser tools. Every new role gets a separate folder; repeated names get a suffix without replacing
previous work. Existing applications can be revised deliberately while preserving submitted versions.

The launcher preserves originals and extracts text; the agent builds the actual profile/template.
Text and DOCX extraction use Python's standard library. Missing PDF dependencies are installed in a
private virtual environment; neither `uv` nor a global Python package install is required.
Scanned PDFs require local OCR or another readable export; legacy `.doc` needs conversion to `.docx`,
PDF, or text. Import status and limitations are recorded separately from profile readiness.

Ask your agent to tailor for the chosen workspace and application folder. It reads the evidence,
writes `cv.html` and `match.md`, and runs:

```sh
skills/tailor-cv/scripts/render.sh workspaces/my-profile/applications/company_role-title --style workspaces/my-profile/profile/style.css
```

Use the actual folder printed by `new` (run `./rolekit new --help` for details). The render wrapper
automatically prepares `pypdf` and uses an installed Chrome/Chromium or downloads a private Chromium
when absent. `ROLEKIT_CHROME` or `CHROME_BIN` can override browser discovery. Direct Python usage
works with dependencies already installed; Windows can run `python skills/tailor-cv/scripts/render_auto.py`.
The renderer checks one page and extractable text, embeds the
style, and writes a hash-backed `render.json`. Your agent also inspects the PDF visually.

## Structure

```text
skills/onboard-candidate/     Guided first-time setup, CV/notes intake, and source preservation
skills/tailor-cv/             Portable skill, blank templates, helpers
  SKILL.md                   Canonical agent-neutral instructions
  references/                Tailoring, workspaces, applications
  assets/profile/            Blank candidate profile and CV template
  scripts/                   Workspace CLI and local PDF renderer
skills/job-search/            Source discovery, screening, and application coordination
  scripts/search.py          Local duplicate/attempt ledger (no browser or network code)
workspaces/                  Private candidate data, excluded from Git
  <person>/
    rolekit.json             Explicit candidate and relative paths
    profile/                 Truth, master CV, preferences, sources
      experiences.md         Full experience library with original-source citations
      cv_style.md            Observed design and template reconstruction limits
      review.md              Onboarding state, conflicts, and unanswered questions
    evidence/                Copied records, not links to another repository
      inputs/                Original CVs/notes, text extracts, and import metadata
    applications/<role>/     JD, CV, match notes, answers, status, receipts
    search/                  Private source configuration, decisions, runs, and SQLite ledger
    migration/               Import provenance and checksums when applicable
```

`profile/sources.json` lists sources in search order. Evidence supports claims; preferences and
strategy guide emphasis; previous CVs are examples to verify. A job requirement cannot create a
new qualification. Direct reports, functional leadership, and people trained remain distinct.

Automatic setup stores candidates outside the skill installation: macOS local Application Support,
Windows Local AppData, or Linux's local data directory, under RoleKit. Workspaces are separate from
managed Python environments and browser downloads. `ROLEKIT_DATA_DIR` can override this location.
No global active candidate is saved. Existing explicit workspaces remain supported.

## Use the skill elsewhere

Copy the **entire** `skills/onboard-candidate/` and `skills/tailor-cv/` folders into your agent's skills
directory as siblings. Add `skills/job-search/` for the complete setup-to-search workflow. Keep each
folder's scripts, references, and assets together. `tailor-cv` can also work alone with an existing
workspace or its simpler conversational setup instructions.

For example, Claude Code can use `.claude/skills/` in a project or `~/.claude/skills/`; this repository
also supplies `.agents/skills/` for Codex project discovery. Do not replace an existing skill without
reviewing it. No global agent configuration is changed. An agent without skill discovery can read
SKILL.md from any location and use the same workflow against an explicitly selected workspace.

Share the skill/code, not your workspace. Workspaces under this repo are ignored automatically;
if you put them elsewhere, their storage and backup are your responsibility. Ignored data is not
backed up by a Git commit. No private record is included in the code history or a release artifact.

The host agent needs Python 3.10+ execution and private file access; it can use a bundled Python when
available. First-time dependency/browser downloads need network access. If a host blocks them, the
agent preserves your originals, reports the actual limitation, and continues useful conversation.
It does not silently claim that extraction or PDF export succeeded.

## Application assistance

The skill includes form preparation and a record format for future browser-assisted applications.
Use the browser capability provided by the host agent. CV tailoring creates local files; uploading,
sending, or submitting requires authorization for that action. The workflow preserves exact answers,
files, and confirmation evidence and distinguishes unknown history from a verified submission.
The host agent supplies browser/email access and the schedule; RoleKit supplies the workflow,
candidate records, and local helpers.

## Search sources and prepare applications

Open RoleKit in your agent and say:

> Use job-search with workspaces/my-profile. Watch these sources: [URLs]. Find roles that match
> my goals and evidence, then use tailor-cv to prepare the strongest applications.

Read [the search skill](skills/job-search/SKILL.md) for the full workflow. Set up private
`search/config.json`, `profile/search_brief.md`, and `profile/application_facts.md` using its blank
assets. The search brief keeps current objectives and hard constraints separate from experience
evidence. A generic role at an attractive company does not automatically qualify.

The default mode is `prepare`. External submission needs specific user authorization for the
candidate, role or bounded policy, materials, and actions, subject to the host's permission rules.
Standard application email verification can use the authorized inbox transiently. New consequential
facts, access-control challenges, payment, or contractual requirements may require the user.

The ledger deduplicates known ATS URLs, imports existing submitted/unknown manifests conservatively,
and locks an application before a submission attempt. It stores exact artifact hashes and outcome
evidence. After a timeout, preserve the unknown result and reconcile receipts before retrying.
Read older company folders too: a legacy record without a posting URL cannot be deduplicated reliably.

```sh
python3 skills/job-search/scripts/search.py ingest workspaces/my-profile --items workspaces/my-profile/search/run-items.json
python3 skills/job-search/scripts/search.py list workspaces/my-profile
```

The helper does not scrape or judge jobs. The agent reads live sources and employer JDs and records
its fit decisions. A recurring Codex or other host task can invoke the same skill. A daily schedule
must be configured separately with the host's scheduling tools and tested with its browser/email
access. Quiet runs should stay quiet when no meaningful opportunity or action changes.

Install or share all three sibling skill folders for the complete onboarding-to-application workflow.
Each person uses their own private source lists, preferences, inbox identity, and application history.

## Migration and verification

[Migration notes](docs/migration.md) explain the extraction and importer. Runtime use does not need
the original repository. The importer supports the original personal_brain layout, copies current
filesystem contents (including untracked work), dereferences local source links, and records hashes.

```sh
python3 tools/import_personal_brain.py --source /path/to/personal_brain --workspace workspaces/my-profile --name "Your Name"
python3 tools/import_personal_brain.py --workspace workspaces/my-profile --verify
```

An import refuses an existing workspace. To compare against the original as well, pass `--source`
to the verify command. Read the private `profile/review.md` before treating old claims as current.

## Development

```sh
python3 -m unittest discover -s tests -p 'test_workspace.py' -v
python3 -m unittest discover -s tests -p 'test_intake.py' -v
python3 -m unittest discover -s tests -p 'test_setup.py' -v
python3 -m unittest discover -s tests -p 'test_render_setup.py' -v
python3 -m unittest discover -s tests -p 'test_search.py' -v
uv run --with 'pypdf==6.20.1' python -m unittest discover -s tests -v
```

The renderer uses local Chrome; it does not send CVs to a remote rendering service. Skill instructions
and evidence do not depend on one model vendor. Browser capabilities and document extraction depend
on the host agent, and a plain text-only agent cannot render or operate an application form.
