# AGENTS.md

This repository *is* an agent skill. The skill body lives in `SKILL.md` — read it before acting on any coding task in this repo.

## Repo map

| File | Purpose |
| --- | --- |
| `SKILL.md` | The skill itself: frontmatter (`name`, `description`) + the maximum-rigor protocol. |
| `skills.sh` | Symlinks this directory into each supported agent's skills folder. |
| `README.md` | Human-facing docs: what it does, install, usage. |
| `banner.svg` | Header image used by the README. |

## Rules for changes here

1. `SKILL.md` frontmatter must stay valid: `---` on line 1, `name:` matching the directory name, and a `description:` written as *"Use when ..."* trigger conditions.
2. Keep `SKILL.md` under ~200 lines. It is loaded into every agent's context; every line costs tokens on every run.
3. Any behavior change in `SKILL.md` that alters what the skill promises must be mirrored in `README.md`.
4. `skills.sh` is POSIX-ish bash and must pass `shellcheck skills.sh`. New agents go in the `TARGETS` array — nowhere else.
5. No new dependencies, build steps, or package manifests. This repo is text plus one shell script by design.

## Verifying

```bash
shellcheck skills.sh          # lint (local only, not in CI)
head -1 SKILL.md              # must be ---
./skills.sh                   # idempotent; re-running must not break existing symlinks
```

CI (`.github/workflows/ci.yml`) checks the docs only: `SKILL.md` frontmatter and that links in `README.md` / `AGENTS.md` resolve. There are no test suites here — keep it that way.

## Contributing flow

`main` is protected: force-pushes and deletions are blocked, history is linear, and CI must pass. Work on a branch, open a PR, let `docs` go green, then squash-merge.
