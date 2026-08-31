# Handoff

## Current state

- Architecture baseline: approved
- Implementation target: GitHub-first V1
- Repository: https://github.com/shifenghe579-collab/codex-engineering-os
- Active task: T001 merge-gate hardening
- Task state: MERGE_READY
- Implementation SHA: `5e85046e59953516b7d0898223dc3b2e2fa5c655`
- Integration candidate SHA: `a2cca6afbd19cfa253f01450d666661471449ed9`
- Reviewer: APPROVED
- Verifier: PASS
- GitHub Environments: administrator bypass disabled for product-approval, governance-approval, and production

## Resume procedure

新 Main 应依次读取：`AGENTS.md`、`governance/WORKFLOW.md`、`PROJECT.md`、`SPEC.md`、`ARCHITECTURE.md`、当前 Task Contract 和 Evidence。

## Blocking follow-up governance work

- T002: bind `integration_candidate_sha` and Evidence freshness to the pull-request HEAD or prove that later changes are bookkeeping-only. Product development remains blocked until this is enforced.
- T003: make `CHANGES_REQUESTED` reachable from review-related states and decide whether Task `id` and `kind` are permanently immutable.

## Next checkpoint

Push the T001 branch, pass every required GitHub check and human Environment approval, squash merge, then perform post-merge verification before marking T001 complete.
