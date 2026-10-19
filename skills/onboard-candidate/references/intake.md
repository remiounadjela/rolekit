# Candidate intake and handoff

## Automatic setup

The agent runs `scripts/start.sh --cv <uploaded-file>` (or `python scripts/start.py` on Windows).
This combines private workspace creation, dependency preparation, and original-file import. It does
not generate career facts or a CV; continue the profile-building instructions after setup.

Names and paths are optional. Without `--workspace`, each invocation creates a new opaque workspace
under the current user's local data directory: macOS `~/Library/Application Support/RoleKit`, Windows
`%LOCALAPPDATA%/RoleKit`, or Linux `$XDG_DATA_HOME/rolekit` (default `~/.local/share/rolekit`). Workspaces
are under `workspaces/`; Python environments and browser downloads are separate. `ROLEKIT_DATA_DIR`
overrides the root for managed hosts or tests. No private data is written into installed skill folders.

Always retain the returned workspace path in the chat and pass it explicitly for later additions.
There is no global active profile and no name-based workspace matching. An explicit existing workspace
is a deliberate resume, with validation and no reinitialization. New users do not need to name or
choose a directory; the agent records the selection automatically. A name absent at launch can be
filled in from an unambiguous CV or the conversation. Original import metadata remains a snapshot.

Text and DOCX extraction need no third-party packages. For PDF input, the launcher reuses a compatible
Python dependency or creates a private venv and installs pinned `pypdf`. No `uv`, system Python
modification, global pip, browser installation, or OS package manager is required to begin onboarding.
`render.sh` later prepares PDF export automatically, using existing Chrome/Chromium when available
or a private Playwright-managed Chromium when absent. It never installs privileged OS dependencies.
Managed downloads follow [Playwright's browser installation](https://playwright.dev/python/docs/browsers).

Inspect `setup_status`, imported-input statuses, issues, and `next_action` in the JSON result. If
network or host restrictions prevent automatic dependency setup, originals still remain preserved
with explicit extraction limitations. Use the host's existing local PDF reader/extractor when
available, record that method separately, and continue useful conversation. Do not describe failed
setup as complete or ask the novice user to diagnose package managers. Only report a technical
blocker when available host capabilities cannot complete the necessary step.

The host must be able to execute Python 3.10+ and write private local files, or provide equivalent
attachment/document tools. Use a host-bundled Python when `python3` is absent. A text-only agent
cannot create local workspaces or render PDFs; explain that actual limit without claiming success.
Installing skills alone does not grant file/shell capabilities or bypass host restrictions.

## Inputs and extraction limits

The importer copies original bytes into a collision-safe folder under
`evidence/inputs/<label>/`, writes `extracted.md` and `input.json`, and registers the extract in the
workspace's declared source map. Labels can be supplied with `--label`; repeated names create new
folders. Original filenames, hashes, capture times, extraction methods, and issues stay private.
It never writes the active profile or creates a tailored CV. Use the printed paths for later work.

| Supplied input | Handling | Limits to disclose |
|---|---|---|
| Markdown or text CV | Copy exact bytes; read the UTF-8 extract | Formatting intent may be described in text; no visual layout is established |
| Word `.docx` | Copy original; extract text locally from OOXML | Tables/layout, drawings, tracked changes, text boxes, or embedded content may need a separate visual check |
| PDF | Copy original; extract page-labelled text with local `pypdf` | Reading order, columns, symbols, and images need visual review; image-only pages need OCR |
| Legacy Word `.doc` | Ask for a `.docx`, PDF, or text export | The bundled helper cannot parse the binary format |
| Notes or speech-to-text transcript | Preserve verbatim as `.md` or `.txt`; import as `experience` | Names, numbers, dates, and speaker attribution may need clarification |
| Audio without a transcript | Use an available host transcription tool within the request's scope | The bundled importer has no speech recognizer; if unavailable, ask for transcript or dictated text |
| Nothing yet | Save the candidate's conversational answers as new dated input snapshots | Do not require a CV, employer, degree, or formal work history |

The normal user path goes through `start.sh` so dependencies are automatic. For advanced callers
using `import_input.py` directly, PDF extraction needs the same pinned dependency used by the renderer.
Use the Python runtime returned by the launcher, or an existing dependency environment:

```sh
uv run --with 'pypdf==6.20.1' python <skill-dir>/scripts/import_input.py <workspace> <input.pdf> --type cv
```

The automatic launcher does not need `uv`; it uses a private virtual environment when necessary. Unsupported
formats fail before import. Supported originals remain preserved if extraction fails; inspect the
reported issues and `input.json` before proceeding. A nonzero result can therefore still have saved
an original. An import with partial or unreadable text is not a complete extraction. Do not work
around missing text by guessing or using an incomplete CV as the full record.

Use the host's local preview, document extraction, or OCR tools when available and needed. Save
any alternate extraction separately with its method and source reference; do not replace the raw
snapshot. Do not upload private materials to an external conversion service simply to get a template.
Treat links in inputs as provenance; do not fetch old repositories as a runtime requirement.

## CV template and facts

The original CV serves two distinct purposes: a candidate-provided account of their career and,
when visible, a design reference. Keep that distinction in the resulting profile:

- `master_cv.html` and `style.css` form the editable baseline. Rebuild structure and visual choices
  rather than embedding an image of the old CV. Preserve meaningful sections, hierarchy, links,
  and candidate style where possible. Keep text selectable. Do not promise pixel-exact conversion.
- `cv_style.md` records the source, observed section order/design, preferences, and what was actually
  inspected. Without a visual view, record content-only reconstruction and the default style.
- `experiences.md` retains the broader factual material from both the CV and the brain dump.
  Brain-dump details can add work absent from the CV; the CV does not cap the candidate's history.

When adapting the bundled HTML/CSS, preserve its `--scale` sizing hook and relative font sizing so
the one-page renderer can fit the result. Keep the template self-contained: no scripts, remote
stylesheets, or remote font/image loads. Do not carry active content from a supplied document into it.

For a source CV with multiple pages, preserve its full content in inputs and the library. The
RoleKit renderer verifies a one-page output; do not silently promise that it will reproduce a
multi-page source. A role-specific one-page CV is selected later. An explicitly requested different
format follows the `tailor-cv` renderer limitations.

Use `candidate_reported` for candidate-supplied CV/notes/statements, `documented` where a cited
supporting record establishes the particular claim, `uncertain` for incomplete or qualified facts,
and `conflicting` for incompatible accounts. Supporting records may themselves be self-authored;
describe what they establish. These labels are attribution, not a numeric confidence score.
Keep original qualifiers such as "about", "we", "helped", "forecast", and "up to". Clarify
individual vs team contribution and direct vs functional management without promoting the wording.

Register the raw CV as `kind: example` (done by the helper); it must not become independent proof
merely by being copied into the library. Candidate-reported history can seed the baseline while
remaining attributed. Ask about disputed or consequential unsupported assertions before using them
in a final CV. A newer document is not automatically the correct one.

## File contract

`rolekit.py init` creates blank profile files. The new keys `experiences`, `review`, and `cv_style`
are optional for existing workspaces. When those keys are present, use their declared relative paths;
otherwise add the files at the default paths and declare them in the profile object, without
overwriting unrelated manifest fields. Each experience entry needs a stable ID and source locations;
the blank `experiences.md` shows a useful shape, not a questionnaire to force on the candidate.

Keep `profile/sources.json` entries portable and workspace-relative. After the experience library is
populated, register it once, preserving existing entries and using an unused ID, for example:

```json
{
  "id": "experience-library",
  "path": "profile/experiences.md",
  "kind": "evidence",
  "priority": 5,
  "note": "Derivative experience index; follow original source citations. Candidate reports remain self-reported, not independently verified."
}
```

Do not add blank prompts as evidence or register a whole directory that includes other candidates.
Avoid circular citations: cite a raw extract's page/paragraph/line or a supporting record for a claim,
not a generated CV that was written from the same claim. A `match.md` created later should retain
this attribution rather than presenting the library as a second corroborating source.

## Resume and finish

On a later brain dump, preserve a new snapshot, add or update the relevant experience entries, and
record contradictions in review notes. Keep stable experience IDs; do not replace the old input or
rewrite submitted CVs. Add only facts actually supplied or supported. Current preferences belong in
`about.md` or a later search brief, separately from experience.

Use these onboarding states in `review.md`:

- `not_started`: blank initialized profile.
- `draft`: inputs collected but no usable baseline/library yet; list the specific blockers.
- `usable_for_tailoring`: usable baseline and source-linked library, with remaining questions recorded.

Unknown optional details do not prevent a usable profile. If the candidate has only education,
volunteering, personal projects, or career-change experience, use those actual records without
inventing employment. An empty initialized template or a successful `doctor` command is insufficient
for `usable_for_tailoring`. Rendering, candidate approval, and application submission are separate
states and are not implied by onboarding readiness.
