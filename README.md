<p align="center">
  <img src="banner.svg" alt="code-max: evidence, or it didn't happen" width="100%">
</p>

# code-max

An agent skill for implementing, debugging, reviewing, refactoring, and migrating code
where correctness matters. It asks for the smallest complete solution, proof that matches
the risk, and an honest `COMPLETE` / `PARTIAL` / `BLOCKED` report.

## How it works

- **Three modes.** Focused, Substantial, and High-risk. The mode sets how much process
  applies, so a small fix doesn't get migration-level ceremony. High-risk triggers (auth,
  payments, migrations, concurrency, public APIs, and others) are listed explicitly.
- **One loop.** Inspect, pin the contract and invariant, get a baseline, change the smallest
  coherent slice, then verify. A failure is sorted as an implementation defect, a bad
  assumption, an environment problem, or an ambiguous contract, and the agent loops back
  to the matching step.
- **Evidence scaled to risk.** Pre-fix evidence, recorded commands, and independent review
  scale with the mode. A skipped or unavailable check never counts as a pass.
- **References on demand.** [Quality gates](references/quality-gates.md) for affected
  domains and a [report template](references/report-template.md) for non-trivial work.

## Install

Copy or symlink this directory into your agent's skills folder as `code-max`, for example:

```bash
git clone https://github.com/PyModel/code-max.git
ln -s "$PWD/code-max" ~/.claude/skills/code-max
```

Other hosts use their own skills paths: `~/.agents/skills`, `~/.cursor/skills`,
`~/.gemini/skills`, `~/.pi/agent/skills`, or `~/.config/opencode/skills`.

## Use

```text
Use code-max to fix the token refresh race. Preserve existing APIs.
Use code-max for a read-only review of the payment retry path.
```

The skill says to skip trivial edits.

## Limits

Instructions can't force an agent to comply or sandbox what it runs, so you still need host
permissions, code review, and CI. The skill grants no authority to push, deploy, or override
project rules.

## License

[MIT](LICENSE)
