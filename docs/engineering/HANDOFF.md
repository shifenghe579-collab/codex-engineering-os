# Handoff

## Current state

- Architecture baseline: approved
- Implementation target: GitHub-first V1
- Repository: https://github.com/shifenghe579-collab/codex-engineering-os
- Active task: T004 lifecycle impact consistency correction
- Task state: INTEGRATION_VERIFYING
- Contract version: 2
- Base SHA: `00f8a106ce24ebe366798438716fd8e551659496`
- Implementation SHA: `f9221339125839f11753e6ca0f49289c95c4565d`
- Integration candidate SHA: pending
- Reviewer: APPROVED
- Verifier: PASS
- T002 substantive merge SHA: `00f8a106ce24ebe366798438716fd8e551659496`
- T002 post-merge Actions: `33462130233` (SUCCESS)
- T002 lifecycle state: pending T004 correction
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

Commit the T004 integration candidate, bind integration evidence to its exact SHA, then create the merge-ready recording commit and run explicit main/head validation.
