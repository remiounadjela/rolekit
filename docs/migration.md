# Standalone extraction

The migration is a filesystem copy into a new repository and an ignored candidate workspace. It
makes no edits in the source repository. The shared code contains a general skill and blank
candidate templates. Personal records, original commands and policies, application outputs, and
migration checksums stay private in `workspaces/<candidate>/`.

The legacy importer deliberately copies the **full local document search fallback**, alongside the
curated records used by the original playbook. A smaller handpicked extract would lose the ability
to find evidence for unexpected job requirements. The import includes the full CV tree, source
Markdown corpus, performance exports, architecture notes, relevant internship records, and supporting
advisory materials. It preserves historical coaching as context, not current instructions.

The importer excludes unrelated communication systems, remote attachments not present locally,
original Git history, OS metadata, and unreferenced third-party CVs. It snapshots symlink targets
as regular files so the original checkout can be unavailable during normal use. Original URLs and
textual paths in archived documents remain provenance; they are not runtime path dependencies.

A private `migration/manifest.json` hashes every imported raw file and records its original relative
path, byte count, and any resolved symlink. It also hashes the operational application copies.
Verification works without the old repository and can optionally compare the originals again.

The active profile and application copies adapt only where required for portability and factual
clarity. CSS is embedded in operational HTML. Historical application/submission stages start unknown.
Known conflicting dates, mislabeled sources, or unsupported outcomes are recorded in the private
profile's review notes; the original bytes remain available in the evidence snapshot. Old templates
and scope policies are historical data, not the reusable skill's instructions.

For a new person, use `rolekit init`, not this migration adapter. An existing CV and supporting
project/review records are enough to begin. There is no requirement to use the original repository's
biography, employer data, strategy, or file layout.
