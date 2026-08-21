<p align="center">
  <img src="banner.svg" alt="code-max" width="100%">
</p>

<p align="center">
  <a href="SKILL.md"><img src="https://img.shields.io/badge/type-agent%20skill-0b0e14?style=flat" alt="agent skill"></a>
  <a href="skills.sh"><img src="https://img.shields.io/badge/works%20with-any%20coding%20agent-5ee2a0?style=flat&labelColor=0b0e14" alt="any coding agent"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-8b98a8?style=flat&labelColor=0b0e14" alt="MIT"></a>
  <a href="https://skills.sh/PyModel/code-max"><img src="https://skills.sh/b/PyModel/code-max" alt="skills.sh installs"></a>
</p>

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
npx skills add PyModel/code-max
```

Installs into whichever agents the [`skills`](https://github.com/vercel-labs/skills) CLI finds on your machine. Update later with `npx skills update code-max`.

Or clone and symlink it yourself:

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
