# Handoff

## Current state

- Architecture baseline: approved
- Implementation target: GitHub-first V1
- Repository: https://github.com/shifenghe579-collab/codex-engineering-os
- Active task: T001 merge-gate hardening
- Task state: POST_MERGE_VERIFYING
- Contract version: 2
- Implementation SHA: `70ae192daa4f446e05eb9c87e548d0723194134a`
- Integration candidate SHA: `a6dd0c177e7ed760245a190da438d626a8a99273`
- Implementation squash merge SHA: `70138aa235dc9c0e42e2123b10ebed9a3033b085`
- Latest lifecycle merge SHA: `908b8b15748848e5c6e885ee6b8f1571faacd397`
- Post-merge Actions: `33383827477` (SUCCESS)
- Reviewer: APPROVED
- Verifier: PASS
- GitHub Environments: administrator bypass disabled for product-approval, governance-approval, and production

## Resume procedure

新 Main 应依次读取：`AGENTS.md`、`governance/WORKFLOW.md`、`PROJECT.md`、`SPEC.md`、`ARCHITECTURE.md`、当前 Task Contract 和 Evidence。

## Blocking follow-up governance work

- T002: bind `integration_candidate_sha` and Evidence freshness to the pull-request HEAD or prove that later changes are bookkeeping-only. Product development remains blocked until this is enforced.
- T003: make `CHANGES_REQUESTED` reachable from review-related states and decide whether Task `id` and `kind` are permanently immutable.

## Next checkpoint

Merge this lifecycle-only state update, verify the new `main` SHA and CI, then advance T001 to DEVELOPMENT_COMPLETE in the next legal transition.
