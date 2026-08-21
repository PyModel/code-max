# code-max

[![Skill](https://img.shields.io/badge/type-agent%20skill-black?style=flat)](SKILL.md)
[![Agents](https://img.shields.io/badge/agents-claude%20%7C%20codex%20%7C%20cursor%20%7C%20gemini%20%7C%20pi%20%7C%20opencode-blue?style=flat)](skills.sh)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)

An agent skill that stops a coding agent from telling you it finished when it did not.

## What it does

Coding agents like to say "done" after writing code they never ran. code-max replaces that habit with a contract:

- Nothing is claimed unless it was observed. No invented command output, no invented test results.
- No TODOs, stubs, or deferred edge cases left behind.
- Tests and builds run after the last edit, not before it.
- Failing checks get fixed at the cause. Rewriting an assertion to go green is a failure, not a shortcut.
- Changes stay inside the requested scope. Your uncommitted work is left alone.
- Instructions found inside repository files are treated as data, not orders. Anything that tries to relax verification gets reported with its `path:line`.

Every run ends with a fixed report: status, requirements, changed files, commands actually executed, pre-existing failures, and open risks. The status is either `COMPLETE` or `BLOCKED`, and `BLOCKED` needs a real external reason such as missing credentials or unreachable infrastructure.

## Install

```bash
git clone https://github.com/PyModel/code-max.git
cd code-max
./skills.sh
```

`skills.sh` symlinks this directory into the skills folder of every agent it knows about:

| Agent | Path |
| --- | --- |
| Claude Code | `~/.claude/skills/code-max` |
| Codex | `~/.codex/skills/code-max` |
| Cursor | `~/.cursor/skills/code-max` |
| Gemini | `~/.gemini/skills/code-max` |
| Pi | `~/.pi/skills/code-max` |
| OpenCode | `~/.config/opencode/skills/code-max` |

Because they are symlinks, `git pull` updates every agent at once. Add or remove entries by editing the `TARGETS` array at the top of the script.

## Use

Ask for it by name, or describe the rigor you want:

```
/code-max fix the token refresh race in src/auth/session.ts
```

```
Implement the CSV import. Verify before you claim done, no stubs.
```

Reach for it when a wrong answer is expensive: migrations, auth, payments, anything you plan to merge without reading closely. For a one-line typo fix it is overhead.

## License

MIT
