# Evidence-first delivery report

Use the project's existing issue/PR format when it carries the same facts. Omit empty
sections and scale detail to risk. Never publish secrets, personal data, or raw sensitive logs.

```text
Status: COMPLETE | PARTIAL | BLOCKED
Scope/revision: inspected base, delivered commit or exact working-tree state

Acceptance:
- Criterion -> PASS / UNMET / BLOCKED; direct evidence; remaining dependency

Changes:
- File/symbol -> root cause, implemented behavior, compatibility impact

Verification:
- Command or concrete manual check -> observed result; environment; final-state coverage
- Distinguish FAIL, NOT RUN, WAIVED, and NOT APPLICABLE from PASS

Findings:
- Severity; verified defect or hypothesis; location; impact; fixed or next action

Operations:
- Dependencies; observability; migration; rollout; rollback; inapplicable areas and reason

Limits:
- Material unknowns, unavailable checks/reviews, pre-existing failures, owner waivers
- Exact unmet work and what would unblock it
```

For measurements, include the workload, versions, hardware/environment, repetitions, and
variance where available. For a bug, link the reproducer/regression test and actual result.
For remote writes, verify the branch/commit/PR state rather than reporting only an attempted
write. A locally passing suite, a pushed branch, a merged PR, and a deployed service are
four different claims, each needing its own evidence.
