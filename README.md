<p align="center">
  <img src="banner.svg" alt="code-max: evidence, or it didn't happen" width="100%">
</p>

# code-max

A portable engineering skill for evidence-backed implementation, debugging, review,
refactoring, and migrations. It demands the smallest complete solution, relevant tests,
and an honest report instead of unsupported claims that work is finished.

## Engineering contract

The [core protocol](SKILL.md) requires an acceptance ledger proportional to the task,
source inspection, preservation of user-owned work, cause-level fixes, and verification
after the last relevant edit. It adds architecture discovery, explicit dependencies and
contracts, risk-based quality gates, prompt defect reporting, small reviewable commits,
and migration/rollback planning where relevant. It reuses existing code before writing new
helpers, stops and reports checks that contradict the contract instead of gaming them, and
scopes independent review to correctness so review findings do not drive over-engineering.
It keeps agents inside the workspace, never prints environment values or credentials, runs
a bug reproducer red before editing, states when no independent review ran, and reports
only check results it observed. The [2026-09 research round](docs/research/2026-09-24-coding-agent-enforcement.md)
and the [first model evaluation](evals/results/2026-09-24-summary.md) (pi with Grok 4.7 and
Claude Sonnet 5) record the evidence; the rules added after that evaluation are not yet
re-measured.

It adapts to the repository rather than imposing a stack, framework, microservices,
coverage percentage, or new toolchain. [Conditional quality gates](references/quality-gates.md)
cover architecture, APIs, data, concurrency, resource cleanup, security/privacy, UI and
accessibility, performance, supply chain, and operations. Load only applicable guidance.

`COMPLETE` requires current evidence for every authorized acceptance item. `PARTIAL`
retains named unfinished work. `BLOCKED` identifies a concrete constraint. Waived, failed,
and unrun checks never become passes. See the [report template](references/report-template.md).
Explicitly requested scaffolding is allowed but cannot be sold as implemented functionality.

**Limits:** Instructions cannot guarantee agent compliance or sandbox execution. Host
permissions, review, and project CI remain necessary. The skill does not grant authority
to push, deploy, change permissions, or override project governance. Automated checks in
this repository validate the package and utilities, not every downstream codebase or model.

## Install

The skill itself is Markdown with no runtime dependencies or hooks. Review it before
loading. Install the whole directory, including references, using your host's supported
skill mechanism. Command syntax and discovery differ between hosts.

For an inspected local checkout, the optional installer needs Python 3.10+ and Bash:

```bash
git clone https://github.com/PyModel/code-max.git
cd code-max
./skills.sh --list
./skills.sh --agent claude --dry-run
./skills.sh --agent claude
```

Choose only the hosts you need. Repeat `--agent` or give an absolute custom **parent skills
directory**, not the final code-max path:

```bash
./skills.sh --agent codex
./skills.sh --target "$HOME/custom-agent/skills" --dry-run
./skills.sh --target "$HOME/custom-agent/skills"
./skills.sh --agent claude --uninstall --dry-run
./skills.sh --agent claude --uninstall
```

`python3 scripts/install.py` accepts the same options without the Bash wrapper.
With no target selection the installer exits without changing anything. `--all` explicitly
selects all presets; it does not detect installed agents. Uninstall removes links to
this checkout in every selected target, reports any foreign entry as a preserved conflict,
and then exits nonzero. Hosts that read multiple shared
locations may show duplicates, so prefer selecting a single appropriate location.

| Preset | Destination |
| --- | --- |
| `claude` | `~/.claude/skills/code-max` |
| `codex` | `~/.agents/skills/code-max` |
| `cursor` | `~/.cursor/skills/code-max` |
| `gemini` | `~/.gemini/skills/code-max` |
| `pi` | `~/.pi/agent/skills/code-max` |
| `opencode` | `${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/code-max` |

These are discovery presets, not a claim that every host/version was integration-tested.
Use `--target` for other hosts or configured paths. Presets require an absolute HOME;
OpenCode also requires XDG_CONFIG_HOME to be absolute when set. Custom targets do not
require HOME. The installed name remains `code-max` even if the checkout is renamed.

Installation preflights all destinations, preserves existing correct links, and refuses
files, directories, foreign links, and dangling links. Link creation is no-clobber. Dry-run
creates no directories or links. Uninstall removes only links resolving to this checkout;
it never deletes the checkout or target directories. There is no force/overwrite option.

Use trusted, user-owned target directories, not directories concurrently modified by an
adversary. Preflight is not a multi-target filesystem transaction: a later I/O failure may
leave earlier reported operations completed. Inspect output and retry idempotently, or
remove the successful links with the same target selection and `--uninstall`. Uninstall
checks ownership before removal but is not a defense against hostile concurrent replacement.

## Migration and update

Older `./skills.sh` with no arguments installed everywhere and could overwrite entries.
Use `--agent` or `--target` now; use `--all` only deliberately. Old Codex and Pi paths were
`~/.codex/skills` and `~/.pi/skills`. Inspect them before removing duplicates; uninstall
an old link with `--target` only while it still resolves to this checkout. Foreign/stale
links are intentionally not auto-deleted. Nothing migrates your host settings or permissions.

Links follow checkout changes. Review updates before pulling, and use a reviewed tag/commit
or separate checkout when you need an immutable installation. To roll back, select a known
good revision in a clean dedicated checkout; do not reset user-owned changes. See the
[hardening audit](docs/hardening.md) for evidence and rollout limits.

## Use

Ask your host to use code-max for substantial or correctness-sensitive work, for example:

```text
Use code-max to fix the token refresh race. Preserve existing APIs and user changes.
Use code-max for a read-only architecture review. Do not edit or publish anything.
```

Use the project's existing test commands, CI, review process, and task tracker. The skill
does not automatically add hooks, copy AGENTS.md into other projects, or execute helpers.
Its description tells hosts to skip trivial edits such as typo fixes or one-line cosmetic changes.

## Contributing and validation

Read [AGENTS.md](AGENTS.md). Optional tools require no third-party Python packages:

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
bash -n skills.sh
shellcheck skills.sh
```

The offline validator checks this repository's restricted two-scalar frontmatter profile,
core line/byte budget, package symlinks, supported local link forms in all Markdown files,
and [scenario definitions](evals/scenarios.json). It is not a general YAML/Markdown parser;
it does not resolve heading anchors, check external URLs, or execute model evaluations.
The installed folder name matches the skill metadata; renamed source checkouts are allowed.

CI preserves the required `docs` check and gates it on Linux/Python 3.10 and macOS/Python
3.13 utility checks, with ShellCheck on Linux. Actions are SHA-pinned with read-only contents
permission and checkout credentials disabled. See [behavioral evaluation](evals/README.md)
for the separate model/host evaluation procedure and its unrun status.

## License

[MIT](LICENSE). Original artwork and historical research remain in the repository.
