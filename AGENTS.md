# Repository guidance

This repo is one agent skill: [SKILL.md](SKILL.md) plus two one-hop
[references](references/). Keep it that way.

- Keep SKILL.md under 200 lines. Frontmatter stays two unquoted single-line scalars:
  `name: code-max` and `description: Use when ...`.
- No scripts, installers, dependencies, or hooks. Detail goes in `references/`.
- Mirror behavioral changes in [README.md](README.md).
- Work on a branch and open a PR; the required `docs` check must pass.
