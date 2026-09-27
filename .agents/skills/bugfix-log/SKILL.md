---
name: bugfix-log
description: Record JanusEdge bug fixes while debugging and fixing repository bugs. Use for bug-fix work, not feature additions, planning, or reviews that do not fix a bug.
---

# Bug Fix Log

Use this skill whenever you investigate and fix one or more bugs in this repository. It supplements the implementation work by recording each completed fix in the active Spec Kit feature folder.

## Resolve the active feature folder

1. Resolve the active feature directory using the repository's Spec Kit path resolver. Run `python -X utf8 .specify/scripts/python/check_prerequisites.py --json --paths-only` from the repository root and read `FEATURE_DIR` from its JSON output. This resolver uses `SPECIFY_FEATURE_DIRECTORY` first, then `.specify/feature.json`, without persisting a new feature pointer in paths-only mode.
2. Confirm that the resolved directory exists and contains the spec being worked on. If resolution fails or the path is not a valid feature directory, ask the user for the active spec directory. Do not guess from old task context or choose among spec folders yourself.
3. Create `<FEATURE_DIR>/bugfix/` if it does not already exist. Do this on every invocation, even if the bug is not ultimately fixed.

## Record completed fixes

- Create one report for each distinct bug actually fixed during this task. Do not write reports for suspected, planned, or unresolved bugs.
- Copy the structure of [bugfix-template.md](bugfix-template.md) into each report and fill in all sections. Keep the report concise and evidence-based; distinguish observed facts from hypotheses.
- Name reports `YYYY-MM-DD-<bug-slug>.md`, using the current local date and a short kebab-case summary. Never overwrite a report; if the name exists, add `-2`, `-3`, and so on before `.md`.
- In **Verification**, list the checks actually performed and their results. State explicitly when relevant checks, including UI checks, were not run.

This skill does not replace the repository's normal bug investigation, implementation, or verification workflow.
