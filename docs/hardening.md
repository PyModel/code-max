# Architecture-neutral hardening audit

Date: 2026-09-04 (America/New_York)
Inspected baseline: `3a7bc44658ff91e57d4a0609734832b627e9e4d0`.
Scope: all nine tracked files, including the CLAUDE.md symlink, installer, CI, skill,
repository guidance, README, license, artwork, and historical research.

## Verified findings and changes

| ID | Severity | Baseline evidence | Resolution |
| --- | --- | --- | --- |
| F1 | High | `skills.sh` used `ln -sfn`. An isolated temporary-HOME reproduction replaced a regular file containing user data. | Exclusive symlink creation; refuse files, directories, foreign and dangling links; no force option. |
| F2 | Medium | With an existing destination directory, the old installer created a nested link and printed success. | Preflight destination types and use no-clobber filesystem primitives; regression includes a simulated directory race. |
| F3 | Medium | `NAME` came from the checkout basename, so a renamed checkout installed a different name from SKILL.md. | Read validated metadata and retain code-max as the installed name. |
| F4 | Medium | The three old CI grep checks accepted a SKILL.md with no closing frontmatter delimiter. | Shared strict metadata reader plus negative-control tests; validate the complete package. |
| F5 | Medium | AGENTS.md expressly prohibited test suites and CI checked only a few text patterns. | Require isolated utility regressions and preserve the existing docs branch-protection context as an aggregate gate. |
| F6 | Medium | Presets used `~/.codex/skills` and `~/.pi/skills`; current primary docs identify `~/.agents/skills` and `~/.pi/agent/skills`. | Correct presets, provide custom targets, document old-link migration without auto-deletion. |
| F7 | Design risk | The 17,158-byte core repeated motivational/scoring language and lacked explicit architecture-adaptation and domain quality selection. | Smaller core with measurable workflow requirements, conditional quality gates, realistic status semantics, and no framework mandate. |

F1-F4 were reproduced against the exact baseline installer/check logic in disposable
paths. The baseline installer bytes matched Git blob
`2b679014ebd4f526284abe171ae8d82a99173741` before execution. This establishes those
failures, not an exhaustive claim that no other defect exists. F5 is verified source/config
behavior; F6 compares documented defaults, not installed-host integration tests. F7 is an
engineering assessment, not a measured model-performance improvement.

The preserved [historical research](research/production-grade-coding-agent-skill-design.md)
records an earlier instruction-only maintenance policy. Its no-tests/no-helper recommendation
is historical, not the current contract. Its prior qualitative model checks were not rerun
or adopted as evidence for this change.

## Target design and acceptance ledger

| Outcome | Implementation | Evidence / limit |
| --- | --- | --- |
| Architecture-neutral rigor | SKILL.md and one-hop references | Source review and context budget; no universal model-compliance claim. |
| Non-destructive installation | Optional Python standard-library helper; Bash entry point | Temporary-HOME regression tests; trusted user-owned directories required. |
| Observable quality gates | Offline package validator, utility tests, required docs aggregate | Local executable checks; remote CI result must be observed separately. |
| Honest behavioral evaluation | Versioned scenarios with expected/forbidden behavior | Scenario schema is checked; model/host runs remain NOT RUN. |
| Safe adoption and reversal | README migration, explicit targets, dry-run, owned-link removal | No automatic migration of host settings or unrelated links. |

The skill remains instruction-only for consumers. Optional installation/maintenance tooling
now requires Python 3.10+, with no pip packages, network access, manifests, hooks, or new
application framework. This is a deliberate trade-off: standard-library filesystem operations
avoid the overwrite and directory-nesting behavior of the prior shell-only implementation.

## Tests and review

Run the maintained commands from the repository root:

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
bash -n skills.sh
shellcheck skills.sh
```

Regression coverage includes file/directory/link conflicts, renamed checkouts, spaces,
relative existing links, symlinked launchers, XDG/HOME validation, explicit selection,
idempotency, uninstall boundaries, dry-run without bytecode writes, malformed and invalid
UTF-8 metadata, recursive/overlapping targets, and a simulated create-time race. Validator
negative controls cover malformed metadata, line/byte budgets, missing files, local links,
encoded traversal, unsafe/dangling symlinks, and invalid scenario definitions.

Implementation review found and repaired dry-run bytecode writes and overlapping target
selection before delivery. The conflict test compares identity, mode, size, modification
and change timestamps, plus file content/directory contents; it deliberately excludes
access time because reading a symlink may update it without modifying the user's entry.

Local validation was performed with Linux, Bash 5.2, and Python 3.13.5. ShellCheck was not
installed locally. The workflow supplies Linux/Python 3.10 and macOS/Python 3.13 checks,
including ShellCheck on Linux. Workflow configuration alone is not a passing remote run.
No independent reviewer or real model/host behavioral evaluation was available in the
editing environment. The PR/check results, rather than this static note, record remote CI.

## Observability, migration, and rollback

Each installer operation reports linked, unchanged, absent, removed, or planned action;
errors identify conflicts. It does not log credentials or inspect the real home directory
in tests. All selected targets are preflighted, but this is not a multi-target transaction.
A later I/O failure can leave earlier reported operations complete. Retry idempotently or
uninstall only successfully created links to the same checkout. Empty directories may remain.

Do not use targets writable by an adversary: uninstall ownership checks cannot eliminate
hostile concurrent filesystem replacement. Existing user-owned symlinked parent directories
are resolved intentionally. This utility is not a privilege boundary or secure installer for
untrusted system locations. Windows-native symlink behavior and real host discovery remain
unvalidated; the no-dependency Markdown consumption path does not require the installer.

For repository rollout, use a review branch and the protected-main PR workflow. Since
2026-09-24 `main` requires a pull request, the `docs` status check on an up-to-date branch,
linear history, and resolved conversations, and these rules apply to administrators too, so
direct pushes and force-pushes are rejected. Required approvals are 0 while the repository
has a single maintainer, because GitHub does not let authors approve their own PRs; raise
the count when a second reviewer exists. Keep the docs status context stable, run CI, inspect the final diff, and merge only under
repository policy. No deployment or database migration is needed. Revert the merged change
through a new PR if necessary; do not rewrite history. Consumers should review updates
before changing their checkout and select a known-good revision in a clean dedicated checkout
for rollback. A link tracks checkout changes, not an immutable release.

## Primary-source basis

- [Agent Skills specification](https://agentskills.io/specification): name/description metadata,
  optional resources, and progressive disclosure. The 200-line/12,000-byte budget is local policy.
- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use):
  minimal token permissions, immutable action references, and untrusted-workflow boundaries.
- [Codex skills](https://developers.openai.com/codex/skills): current user skill discovery path.
- [Claude Code skills](https://code.claude.com/docs/en/skills): personal skill location and host-specific loading.
- [Cursor skills](https://cursor.com/docs/skills): host-specific skill discovery.
- [Gemini CLI skills](https://geminicli.com/docs/cli/skills/): host-specific skill discovery.
- [Pi skill documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md): global vs project skill locations.
- [OpenCode skills](https://opencode.ai/docs/skills/): global and compatible skill locations.

These sources support the packaging and integration choices. They do not prove the new
wording improves every model or that a passing utility suite ensures production correctness.
