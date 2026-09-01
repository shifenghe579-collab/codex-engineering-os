# Handoff

## Current state

- Architecture baseline: approved
- Implementation target: GitHub-first V1
- Repository: https://github.com/shifenghe579-collab/codex-engineering-os
- Active task: T002 evidence freshness and PR-head binding
- Task state: MERGE_READY
- Contract version: 1
- Base SHA: `0988d08978ed70179c80a11a4057e316edeb76c4`
- Implementation SHA: `84d122585cb46a320c0159429e70aab4af4fef80`
- Integration candidate SHA: `a39be20a72ffcc68ce723c789a65812694afd89c`
- Reviewer: APPROVED
- Verifier: PASS
- Completed task: T001 merge-gate hardening
- T001 state: DEVELOPMENT_COMPLETE
- T001 final main SHA: `0988d08978ed70179c80a11a4057e316edeb76c4`
- GitHub Environments: administrator bypass disabled for product-approval, governance-approval, and production

## Resume procedure

新 Main 应依次读取：`AGENTS.md`、`governance/WORKFLOW.md`、`PROJECT.md`、`SPEC.md`、`ARCHITECTURE.md`、当前 Task Contract 和 Evidence。

## Blocking follow-up governance work

- T003: make `CHANGES_REQUESTED` reachable from review-related states and decide whether Task `id` and `kind` are permanently immutable.
- Future: implement the approved design for Codex-conversation user decisions without repetitive GitHub lifecycle approvals.

## Next checkpoint

Commit this candidate-bound integration evidence, validate the resulting PR head against explicit main/head refs, then request merge approvals and CI.
