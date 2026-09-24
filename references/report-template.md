# Report template

Use the project's own PR or issue format when it carries the same facts. Omit empty
sections. Never include secrets, personal data, or raw sensitive logs.

```text
Status: COMPLETE | PARTIAL | BLOCKED
Mode: Focused | Substantial | High-risk

Acceptance:
- Criterion -> PASS / UNMET / BLOCKED; evidence

Changes:
- File/symbol -> root cause, behavior, compatibility impact

Verification:
- Command or manual check -> observed result
- Mark FAIL, NOT RUN, WAIVED, NOT APPLICABLE distinctly from PASS

Findings:
- Severity; location; impact; fixed or next action

Operations (High-risk only):
- Migration; rollout; rollback; observability

Limits:
- Unknowns, unavailable checks or reviews, pre-existing failures, remaining work
```

A passing local suite, a pushed branch, a merged PR, and a deployed service are four
separate claims; each needs its own evidence.
