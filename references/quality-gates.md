# Conditional quality gates

Apply only the rows triggered by the change. These are review prompts, not universal
framework mandates. Select the repository's own commands after inspecting their definitions.
For each selected gate, record the invariant, test/evidence, result, and any remaining risk.

| Change surface | Design and implementation requirements | Evidence to seek |
| --- | --- | --- |
| Modules and architecture | Preserve dependency direction; give each invariant and state transition one owner; keep interfaces explicit and cohesive; avoid circular dependencies and unnecessary abstractions. | Trace entry points/callers, test contracts and integration, inspect final diff for duplicate policy or dead wiring. |
| APIs and input boundaries | Validate type, size, range, encoding, and ownership; preserve error semantics and compatibility; bound pagination and uploads. | Malformed/oversized/empty/boundary inputs, contract tests, consumer compatibility, unauthorized and cross-tenant access. |
| State and persistence | Use appropriate atomicity, constraints, uniqueness, and concurrency control; define ownership and retention; use exact representations where required. | Duplicate requests, lost updates, partial failure, isolation, recovery, and realistic migration tests. |
| Distributed I/O | Propagate deadlines/cancellation; bound retries, concurrency, queues, and connection pools; retry only safe operations within a total budget. | Timeouts, disconnects, duplicate/out-of-order delivery, retry exhaustion, overload, shutdown, and partial success. |
| Resource lifecycle | Pair acquisition with release; avoid unbounded memory/file/socket/task growth; use structured lifetime management supported by the stack. | Error/cancel cleanup, repeated operation, leak checks, race/deadlock tests, deterministic shutdown. |
| Security and privacy | Identify trust boundaries; least privilege; authenticate and authorize each sensitive operation; safe parsing/encoding; no embedded secrets; minimize sensitive data. | Negative access tests, injection/path traversal/SSRF cases where relevant, log redaction, dependency and secret scans available in the project. |
| UI and accessibility | Preserve semantic controls, keyboard/focus behavior, labels, responsive layout, and loading/empty/error/success states; prevent duplicate destructive submissions. | Relevant component and browser tests, keyboard checks, supported viewport/device checks, accessibility tooling and visual review. |
| Performance | Identify the bottleneck before optimizing; measure representative workload and correctness together; prefer complexity/resource reductions supported by data. | Reproducible before/after measurements with hardware, versions, data size, warmup, repetitions, variance, throughput/latency and memory. |
| Build and supply chain | Honor supported versions, lockfiles, generated sources and licenses; minimize permissions and dependencies; isolate untrusted builds from secrets. | Clean build in an appropriate environment, lockfile consistency, platform/version matrix, pinned CI actions and dependency review. |
| Operations and delivery | Make config validation and failure diagnostics actionable; define safe rollout/rollback and observable acceptance thresholds; avoid telemetry with secrets or unbounded cardinality. | Health/readiness, structured errors, relevant metrics/traces, rollback rehearsal, feature gate defaults and recovery instructions. |

## Architecture adaptation

A monolith, library, CLI, batch job, mobile app, infrastructure module, embedded system,
and distributed service need different boundaries and proof. Functional and object-oriented
code can both meet the protocol. Preserve domain vocabulary and local design decisions.
For polyglot repositories, map each affected package to its own toolchain and test command;
a green root command may not include every package. For legacy code, characterize behavior
before changing it. Introduce seams incrementally instead of requiring a wholesale rewrite.
For a documentation-only repository, validate links/examples and any executable utilities;
application-specific gates may legitimately be inapplicable.

## Migration and rollback

Before a state or public-contract change, identify readers/writers, mixed-version operation,
data volume, locks, failure recovery, and the point at which reversal becomes unsafe.
Prefer additive/expand-and-contract rollout when compatibility requires it; do not prescribe
it for every change. Test representative old data and interrupted/repeated execution.
A code revert does not undo deleted data or irreversible external side effects. Document
backup/restore or a forward repair where rollback is not possible. Never execute production
migrations, credential changes, cleanup, or deployment without the necessary authorization.

## Operational evidence

Use existing logs, metrics, traces, and profiling rather than adding a telemetry stack by
default. Define what success and regression would look like before the rollout. Distinguish
measured improvements from hypotheses; record unavailable production validation explicitly.
A local benchmark cannot establish a production service-level objective by itself.

## Exceptions without loopholes

A gate can be not applicable only with a concrete reason tied to the change. A missing
service/tool is an unrun check, not an inapplicable one. A pre-existing failure needs baseline
evidence. A waived check needs the owner's authorization and remaining proof. Coverage and
mutation scores are context-dependent signals, not proof of correctness; report what a check
actually exercised. None permits fabricated output or a blanket assertion that all code
quality requirements are satisfied.
