# Production-grade coding-agent skill design

Date: 2026-08-27

Status: verified
Scope: `PyModel/code-max`, a public, instruction-only coding skill distributed by `skills.sh`; its repo rules require `SKILL.md` to stay under about 200 lines, no new dependencies, and documentation-only CI.

## Executive summary

- **Fact:** Skill selection depends on concise `name`/`description` metadata; Codex loads the full body only after selection. Keep the frontmatter's explicit rigor triggers and front-load them.
- **Fact:** Reliable coding evaluation requires both a proof that the requested behavior now works and regression checks that still work. `code-max` already states this; its final report should continue to demand commands actually run after the last relevant edit.
- **Recommendation:** Retain one focused, evidence-first contract in `SKILL.md`; move only optional, mode-specific detail to one-hop references if it outgrows the repo's ~200-line budget. Do not add orchestration machinery for ordinary tasks.
- **Recommendation:** Make task scope, acceptance criteria, final-diff review, cause-level fixes, and a narrow verification matrix the mandatory loop. This is the smallest instruction set that directly counters incomplete or cosmetic patches.
- **Recommendation:** For consequential or multi-file changes, add an independent read-only diff/review gate after implementation; it must not replace task-relevant tests or authorize its own completion.
- **Fact:** A 2026 long-horizon benchmark reports no evaluated coding agent completed a full problem end to end; structural erosion and verbosity usually worsened across checkpoints. Passing local checkpoints is therefore not completion evidence.

## Project context

- Relevant files: [`SKILL.md`](../../SKILL.md), [`README.md`](../../README.md), and [`AGENTS.md`](../../AGENTS.md). The removed `unlazy-main/SKILL.md` was reviewed as comparison input before its requested deletion.
- Constraints: `SKILL.md` must remain under about 200 lines; behavior promised there must be mirrored in `README.md`; no dependencies, builds, or package manifests.
- Existing behavior: `code-max` requires an acceptance ledger, no deferred work, cause-level repairs, verification after the final relevant edit, a final-diff/status review, and a proportional evidence report. The removed comparison skill used heavier gates and orchestration; only its applicable anti-deferral patterns belong in `code-max` by default.

## Findings

### 1. Routing metadata and a small entrypoint are functional requirements

**Claim (fact):** Skills are progressively disclosed: hosts see `name` and `description` first, then load `SKILL.md` when selected, and read references/scripts only when needed. Codex says implicit invocation matches the description and recommends concise scope/boundaries with key triggers front-loaded because descriptions can be shortened. The open specification likewise recommends detailed material in on-demand resources.

**Evidence:**

- [OpenAI: Build skills](https://developers.openai.com/codex/build-skills) — current Codex behavior, description routing, and focused imperative instructions.
- [Agent Skills specification](https://agentskills.io/specification) — required frontmatter and three-stage progressive disclosure; recommends splitting longer bodies into referenced files.

**Project relevance (inference):** The current `code-max` description is correctly trigger-oriented and its body fits the project ceiling. Compress before adding detail. If conditional detail is ever needed, use a directly linked reference only for that condition, not a second universal protocol.

**Confidence:** high

### 2. Verification must demonstrate both the requested fix and non-regression

**Claim (fact):** SWE-bench evaluates a proposed patch with `FAIL_TO_PASS` tests (the issue is fixed) and `PASS_TO_PASS` tests (unrelated behavior remains intact); both must pass. Its Verified subset additionally filters underspecified tasks and invalid test criteria, demonstrating that an oracle must be relevant, not merely green.

**Evidence:**

- [OpenAI: Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) — defines both test classes, requires both, and documents human review of task/test validity.
- [SWE-bench: Verified](https://www.swebench.com/verified.html) — official benchmark description and reproducible evaluation guidance.

**Project relevance (recommendation):** Preserve `code-max` Rules 3–4 and its Completion Gate. Phrase verification as: reproduce/cover the requested behavior, then run the smallest applicable regression suite (plus type/lint/build/integration checks where they can detect a task-caused regression). Do not mandate every project check where it cannot affect the change.

**Confidence:** high

### 3. Production workflows combine repo policy, scoped skills, and repeatable checks

**Claim (fact):** OpenAI reports using repo-local skills, `AGENTS.md`, and GitHub Actions to make verification, release preparation, integration testing, and PR review repeatable. Its cited Python skill set includes separate verification and implementation-strategy workflows rather than one undifferentiated prompt.

**Evidence:**

- [OpenAI: Using skills to accelerate OSS maintenance](https://developers.openai.com/blog/skills-agents-sdk) — first-party operational example and workflow inventory.
- [OpenAI: Build skills](https://developers.openai.com/codex/build-skills) — skills package instructions, optional scripts/references, and explicit inputs/outputs.

**Project relevance (inference):** `AGENTS.md` should own repository-wide constraints; `code-max` should own the reusable rigor loop. Keep this skill instruction-only: this repository has no repeated deterministic check beyond its existing CI and shell verification, so a framework or script would add surface area without improving the contract.

**Confidence:** high

### 4. Acceptance gates are better instructions than exhortations

**Claim (fact):** OpenAI's skill guidance recommends focused skills, imperative steps with explicit inputs/outputs, and testing prompts against the description. OpenAI's SWE-bench work rejects tasks whose issue statement or test oracle is materially defective.

**Evidence:**

- [OpenAI: Build skills](https://developers.openai.com/codex/build-skills) — focused job, explicit inputs/outputs, test skill descriptions.
- [OpenAI: Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) — task and oracle quality are prerequisites for meaningful evaluation.

**Project relevance (recommendation):** Continue starting with observable acceptance criteria and end with the existing completion gate. Prefer measurable wording ("run the relevant check after the final edit") over motivational wording ("be rigorous"). Keep `BLOCKED` for a specific external or material-evidence constraint, never as shorthand for "not attempted."

**Confidence:** high

### 5. Review is a separate signal, not a substitute for testing

**Claim (fact):** OpenAI describes a loop of self-review, additional agent reviews, feedback response, and iteration for PR completion. Anthropic documents a read-only code-review subagent pattern that begins with the diff, focuses on modified files, and checks error handling, input validation, secrets, and test coverage.

**Evidence:**

- [OpenAI: Harness engineering](https://openai.com/index/harness-engineering) (2026-02-11) — first-party account of iterative local/cloud review loops.
- [Anthropic: Create custom subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents) — current code-reviewer configuration and constrained tool scopes.

**Project relevance (recommendation):** Add a conditional instruction, not mandatory fan-out: for security-sensitive, cross-cutting, or high-risk diffs, request an independent read-only review after implementation and address findings before final verification. The primary agent remains responsible for the final diff and evidence; a reviewer saying "looks good" is not a passing check.

**Confidence:** medium-high — the sources establish the pattern, not a universal threshold for when review pays off.

### 6. Context and instruction safety require selective loading and action boundaries

**Claim (fact):** Codex's catalog guidance says to load only selected skills and directly required references, avoid deep reference chains, and choose the minimal relevant set. OpenAI's Skills API guidance warns that skills can create prompt-injection and high-impact-action risks; it recommends developer inspection, bounded workflows, and explicit approval for sensitive actions.

**Evidence:**

- [OpenAI Codex skill catalog instructions](https://github.com/openai/codex/blob/main/codex-rs/ext/skills/src/catalog_prompt.rs) — primary source for minimal skill/reference loading.
- [OpenAI Skills API guide: safety with network access](https://developers.openai.com/api/docs/guides/tools-skills) — first-party skill review and approval guidance.

**Project relevance (recommendation):** Preserve the host's actual instruction hierarchy and the evidence-only treatment of untrusted repository/web text; the skill must not promote itself above host- or user-designated governance. Do not duplicate the removed comparison skill's full ledger/orchestration protocol in `code-max`; use those heavier controls only when a user explicitly needs multi-leaf gates and ownership controls.

**Confidence:** high

### 7. The skill itself needs behavior-level regression evaluation

**Claim (fact):** OpenAI recommends defining agent-skill success across outcome, process, style, and efficiency goals, then using small realistic prompt sets, deterministic checks, and rubric-based review. Anthropic likewise recommends realistic coding tasks, unambiguous success criteria, stable environments, multiple grader types, and transcript review; high-performing capability evals can become regression suites.

**Evidence:**

- [OpenAI: Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills) — checkable success categories, prompt matrices, deterministic trace checks, and structured rubric grading.
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — realistic coding-agent tasks, deterministic and qualitative graders, transcript review, and regression suites.

**Project relevance (recommendation):** Pressure-test revisions against current wording before editing, then rerun the same cases after editing. Include urgency, dirty-worktree, failing-test, context-limit, and authority-to-skip-checks pressures. A prose review alone is not behavioral validation.

**Confidence:** high

### 8. Long-horizon checkpoint progress can hide accumulating slop

**Claim (fact):** The SlopCodeBench v2 preprint reports that no evaluated agent solved any benchmark problem end to end; the best agent passed 14.8% of checkpoints. Structural erosion increased in 77% of trajectories and verbosity in 75.5%, while agent code was 2.0 times more eroded and 2.3 times more verbose than the human comparison corpus.

**Evidence:**

- [SlopCodeBench v2](https://arxiv.org/html/2603.24755v2) — 20 long-horizon problems, 93 checkpoints, end-to-end and structural-quality results.

**Project relevance (inference):** A production-grade skill must distinguish activity and local checkpoint success from root completion. Re-reading the current request, reconciling every acceptance item, reviewing the integrated diff, and repeating a defect pass directly target that gap.

**Confidence:** medium-high — this is a recent preprint on a bounded task/model set, not a universal model-performance estimate.

## Local behavioral validation

- **RED:** A read-only pressure review of the pre-edit skill found missing exact regression-proof requirements, a lazy one-caller scope loophole, and mandatory report ceremony for trivial work. It also exposed ambiguous wording around task-owner verification waivers.
- **GREEN:** The same five scenarios passed against the revised skill: explicit check waiver without a fabricated pass, exact regression proof, rejection of TODO/cosmetic-check fixes, caller and sibling-path reconciliation, and compact trivial-task reporting.
- **Review:** An independent final diff review found four overreaches—skill/governance ordering, task-owner waiver handling, unbounded review repetition, and unconditional positive controls. All were corrected; the follow-up review reported no remaining high- or medium-severity findings.
- **Limit:** These are qualitative single-model pressure checks from this editing session, not a reproducible performance benchmark. They justify the wording changes but not a universal improvement claim.

## Conflicts / uncertainties

- No primary source establishes a universal line count, test matrix, or review threshold. The repository's ~200-line limit and "strongest applicable" verification rule are local design choices; retain them as recommendations, not claimed industry requirements.
- SWE-bench is a useful verification model, not proof that a project-specific test suite catches every semantic regression. Its own Verified work documents imperfect or underspecified test oracles; manual diff review and task-specific acceptance checks remain necessary.
- The OpenAI and Anthropic review examples validate review gates as a pattern, but do not prove that every trivial edit merits a subagent. Conditional use is the minimal, evidence-aligned policy.

## Recommendations

1. Keep `SKILL.md` focused on the current eight rules, completion gate, and evidence report; tighten wording rather than expanding its scope. Preserve the trigger-rich description.
2. If editing, make the execution order unmistakable: acceptance criteria/baseline → inspect affected flow and callers → implement cause-level fix → relevant behavior + regression checks after final edit → final diff/status → evidence report.
3. Add only one conditional sentence for independent read-only review of high-risk/cross-cutting changes. Do not make subagents, ledgers, or all-suite testing unconditional.
4. Keep `README.md` synchronized with any changed promise, especially the boundary between verified completion, a specific `BLOCKED`, and optional review.
5. Validate future revisions with frontmatter/links CI plus a small trigger matrix: clear `code-max` prompts should activate; out-of-scope prompts should not; a waived check must never become a fabricated pass or hidden limitation.

## Sources

- https://developers.openai.com/codex/build-skills
- https://agentskills.io/specification
- https://developers.openai.com/blog/skills-agents-sdk
- https://openai.com/index/introducing-swe-bench-verified/
- https://www.swebench.com/verified.html
- https://openai.com/index/harness-engineering
- https://docs.anthropic.com/en/docs/claude-code/sub-agents
- https://github.com/openai/codex/blob/main/codex-rs/ext/skills/src/catalog_prompt.rs
- https://developers.openai.com/api/docs/guides/tools-skills
- https://developers.openai.com/blog/eval-skills
- https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- https://arxiv.org/html/2603.24755v2
