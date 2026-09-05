# Repository guidance

This repository distributes an agent skill, not an application framework. Read
[SKILL.md](SKILL.md) before changing it. Follow host instruction precedence and the
user's authorized task. These rules govern this repository, not every consuming project.

## Ownership map

| Path | Responsibility |
| --- | --- |
| [SKILL.md](SKILL.md) | Portable core protocol and activation metadata. |
| [references/](references/) | Directly linked, conditional quality guidance and reporting. |
| [scripts/](scripts/) and [skills.sh](skills.sh) | Optional standard-library Python helpers and Bash entry point. |
| [tests/](tests/) | Isolated utility regression and negative-control tests. |
| [evals/](evals/) | Behavioral scenarios and honest model-evaluation procedure. |
| [README.md](README.md) | Installation, capabilities, limitations, and adoption. |
| [docs/](docs/) | Audit evidence, migration, and historical research. |
| [.github/](.github/) | CI and contribution gates. |

## Change contract

- Inspect the baseline and preserve user-owned work. Record multi-step acceptance work
  in the existing task/PR ledger; do not introduce duplicate trackers for every request.
- Keep the core architecture-, stack-, host-, and tool-agnostic. Do not mandate universal
  frameworks, arbitrary coverage percentages, broad refactors, or unavailable tools.
- Keep SKILL.md at most 200 lines and 12,000 UTF-8 bytes. This is a local context budget,
  not an industry standard. Use one-hop references for optional detail.
- Maintain the minimal frontmatter profile: unquoted, single-line `name: code-max` and
  a `description: Use when ...` scalar. The validator deliberately is not a general YAML parser.
- Mirror behavioral promises, dependencies, CLI changes, and limitations in README.md.
  Update this ownership map or scoped guidance when responsibilities change.
- Preserve the instruction-only consumption path. Optional tooling uses Python 3.10+
  standard library and Bash; no pip/npm dependencies, network calls, or package manifests.
  Do not turn installation into execution hooks or automatically modify host permissions.
- Tests are required for executable behavior changes. Use temporary HOME and explicit
  targets; never test installation against the developer's real agent directories.
- Report every discovered bug with evidence and disposition. Fix in-scope defects; record
  other findings without hiding them or silently expanding scope.
- Make small, coherent, reviewable commits. Stage exact paths and inspect the staged diff.
  Work on a branch and open a PR. Respect the existing required `docs` status context;
  do not bypass branch protection or claim a remote check passed without observing it.

## Verification

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
bash -n skills.sh
shellcheck skills.sh
```

Read [evals/README.md](evals/README.md) for behavioral evaluation. Utility tests and
scenario-schema validation do not prove model compliance. Report model evaluations,
platform checks, lint, and reviews as unrun when they were unavailable.
