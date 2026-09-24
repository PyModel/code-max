# Quality gates

Apply only the rows the change touches. Use the repository's own commands. A gate is
"not applicable" only with a concrete reason; a missing tool or service is an unrun check.

| Surface | Requirements | Evidence |
| --- | --- | --- |
| Architecture | Preserve dependency direction; one owner per invariant and state transition; explicit, cohesive interfaces; no speculative abstraction. | Trace entry points and callers; check the final diff for duplicated policy or dead wiring. |
| APIs and inputs | Validate type, size, range, encoding, ownership; preserve error semantics and compatibility; bound pagination and uploads. | Malformed, oversized, empty, and boundary inputs; consumer compatibility; unauthorized and cross-tenant access. |
| State and persistence | Atomicity, constraints, uniqueness, and concurrency control; exact representations where required. | Duplicate requests, lost updates, partial failure, recovery, realistic migration data. |
| Concurrency | Clear ownership of shared state; atomic check-then-act; cancellation and deadlines propagate; ordering assumptions stated; operations idempotent where retried or redelivered. | Races, duplicate and out-of-order delivery, retry exhaustion, cancellation mid-operation, shutdown, deadlock. |
| Resources | Pair acquisition with release; bound memory, files, sockets, tasks, queues, and pools. | Cleanup on error and cancel, repeated runs, leak checks. |
| Security and privacy | Least privilege; authorize each sensitive operation; safe parsing and encoding; no embedded secrets; minimal sensitive data in logs. | Negative access tests; injection, path traversal, SSRF where relevant; log redaction. |
| UI and accessibility | Semantic controls, keyboard and focus, labels, responsive layout; loading, empty, error, success states; no duplicate destructive submits. | Component or browser tests, keyboard checks, supported viewports, accessibility tooling. |
| Performance | Find the bottleneck before optimizing; keep correctness checks alongside speed. | Before/after on a representative workload with warmup, repetitions, variance, and comparable hardware and versions. |
| Build and supply chain | Honor pinned versions, lockfiles, generated sources, licenses; minimal dependencies and permissions. | Clean build, lockfile consistency, dependency review. |
| Operations | Actionable config errors; defined rollout and rollback; no secrets or unbounded cardinality in telemetry. | Health checks, structured errors, metrics or traces, rollback steps. |

## Migration and rollback

Before a state or public-contract change, identify readers and writers, mixed-version
operation, data volume, locks, and the point where reversal becomes unsafe. Test old data
and interrupted or repeated runs. A code revert does not undo deleted data or external side
effects; document backup/restore or a forward repair. Never run production migrations,
credential changes, or deployments without explicit authorization.

## Legacy and polyglot code

Characterize existing behavior before changing it. Map each affected package to its own
toolchain; a green root command may not cover every package.
