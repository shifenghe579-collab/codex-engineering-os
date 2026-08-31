# Codex Engineering OS

## Authority

- 用户拥有产品语义、Acceptance Criteria 与剩余业务风险的最终决定权。
- `governance/`、本文件、`.github/` 和 `scripts/engineering/` 约束所有 Agent。
- 讨论、审查或提问不授权修改。只有用户明确要求实施时才允许写入。

## Mandatory workflow

1. 修改前读取 `governance/WORKFLOW.md` 和当前 Task Contract。
2. 正式变更必须关联一个 `docs/engineering/tasks/Txxx.yaml`。
3. 不得降低 Risk Floor、Acceptance Criteria 或 Required Gates。
4. Worker 只能修改 Task Contract 明确允许的范围。
5. Reviewer 与 Verifier 不得修改被审查的业务实现。
6. Evidence 必须绑定 Contract 版本和被验证的 Git SHA。
7. Required Gates 未满足时不得宣称 `DEVELOPMENT_COMPLETE`。
8. Governance 实质修改必须使用 `kind: governance` 的独立任务。

## Shared engineering principles

- Think before coding: 明示假设和不确定性。
- Simplicity first: 只实现当前合同要求。
- Surgical changes: 不顺手重构或清理无关内容。
- Evidence over claims: 以 diff、测试、构建、审查和验收证据为准。
