# Candidate workspaces

A workspace can live anywhere local. Inside RoleKit, `workspaces/` is excluded from Git.
Use the workspace established for this candidate in the current chat or explicitly supplied for
resumption. Do not make the user repeat a path already established in this chat. One workspace per
person keeps sources separate; automatic onboarding creates a fresh private one when needed.

```sh
python3 <skill-dir>/scripts/rolekit.py init <workspace> --name "Your Name"
```

The command refuses to overwrite an existing directory. It creates:

- `rolekit.json`: candidate, profile paths, source map, applications path, and page limit.
- `profile/about.md`: contact details, history, preferences, optional application facts.
- `profile/skills_truth.md`: supported skills, gaps, official titles, scope, uncertainties.
- `profile/master_cv.html`: editable baseline, initially a blank template.
- `profile/style.css`: print style.
- `profile/sources.json`: evidence inventory.
- `evidence/`: private records copied or added by the candidate.
- `applications/`: one folder per role.

Onboard from the candidate's existing CV and records. Populate the master CV and guardrails; confirm
uncertain dates and ownership instead of filling them from templates. Preserve raw records as supplied.

For guided CV/brain-dump intake, use the sibling `onboard-candidate` skill when installed. It accepts
PDF, Word `.docx`, Markdown, text, or a dictated transcript and also supports a candidate with no CV.
The agent handles extraction and organization; the candidate need not edit configuration or complete
a structured form. Without the companion, collect the candidate's history conversationally, preserve
verbatim input snapshots under `evidence/`, and populate the same profile files. Use available local
document tools for supplied files and disclose unreadable content or uninspected layout.

New workspaces also contain these optional profile files declared by `rolekit.json`:

- `profile/experiences.md`: the full, source-linked experience library, separate from the one-page CV.
- `profile/cv_style.md`: source design, candidate preferences, and reconstruction limitations.
- `profile/review.md`: onboarding state, extraction coverage, fact conflicts, and open questions.

These keys are optional in older workspaces. Add them deliberately when enriching an older profile;
copy blank assets only for missing files. Respect declared custom paths and preserve existing facts.
Register populated experiences in the source map as a derivative index with original citations and
candidate-report attribution. Do not register blank prompts as evidence. Record onboarding as
`draft` until there is a usable baseline and sourced library, then `usable_for_tailoring`; a structural
`doctor` pass alone does not establish this.

Each source map entry uses a path relative to the workspace root:

```json
[
  {"id":"project-review","path":"evidence/project-review.md","kind":"evidence","priority":1,"note":"My contribution and measured outcome"},
  {"id":"career-preferences","path":"profile/about.md","kind":"context","priority":10,"note":"Positioning only"}
]
```

Use `kind: evidence` for proof; `context` for preferences/strategy; `example` for prior output; `legacy`
for archival policies. Directories are permitted for keyword search. Sources stay inside the workspace;
copy files in rather than adding symlinks to another person's folders or an old repository.

`rolekit.json` stores profile paths relative to the workspace and `sources` points at this array.
Use `inspect` to list the workspace and `doctor` to validate paths and manifests. An init template
still needs actual candidate facts; structural validation is not claim validation.

When a candidate confirms a new fact, update their active profile and record provenance/date where
useful. Do not silently rewrite old source records or another candidate's files.
