# Engineering Workflow

## System invariant

任何一个人、Agent、文档、测试或证据来源都可能出错；任何单个错误来源都不得拥有独立把错误送入最终产品的权限。

## Fixed roles

系统永远只有五个 Agent 角色：

| Role | Responsibility | May not |
| --- | --- | --- |
| Main | 澄清、设计、拆解、调度、集成 | 直接写业务代码、独自放行 |
| Explorer | 只读调查当前事实 | 修改文件、确认产品语义 |
| Worker | 按批准合同实施 | 改合同、扩范围、自审放行 |
| Reviewer | 独立技术审查 | 修改被审实现 |
| Verifier | 独立黑盒验收 | 改实现、重新定义预期 |

Architecture Challenger 是 Reviewer 的 critical mode；Integration Owner 是 Main 在集成阶段的职责，不是新角色。普通子 Agent 不得继续创建子 Agent。

## Authority

- 产品语义、产品 AC、业务取舍：用户。
- 技术方案和集成：Main。
- 最低风险与流程要求：Governance。
- 实现：Worker。
- 技术审查：Reviewer。
- 行为验收：Verifier。
- 合并资格：Required Gates 与所需批准共同决定。

用户不负责裁决复杂技术事实。技术争议由第二次独立技术审查处理；R3 无法证明安全时保持 BLOCKED。

## Requirement gate

正式开发前必须完成：恢复项目事实、调查相关代码、复述需求、集中澄清产品歧义、确认 Acceptance Criteria、固化 Contract v1。

产品行为、业务规则、异常、输入输出、边界、数据、权限、兼容性、性能目标和成功标准存在歧义时必须询问用户。内部实现细节由 Main 主动决定。

`SPEC.md` 只保存用户已确认的规范性要求。推断事实进入 Explorer Result，未决问题进入 Task Contract，当前技术事实进入 `ARCHITECTURE.md`。

## Risk

Final Risk = Governance Risk Floor + Main Escalation。Main 可以升级，不能降到 Floor 以下。

- R0：纯文档或无行为影响的机械变更。
- R1：局部、可回滚、影响边界清晰的普通变更。
- R2：安全、数据、公共契约、并发、跨模块或高回归风险变更。
- R3：生产破坏性、难以回滚或安全证明不足的变更。

R2/R3 在 Worker 开始前必须完成技术挑战和关键 Acceptance Plan。R3 还必须具备回滚或恢复方案，以及用户的剩余风险接受；风险接受不能替代技术证明。

## Worktree dispatch

V1 中 Main 只生成 Dispatch Artifact，用户创建独立 Worktree 任务。普通子 Agent 不等于 Worktree Worker。

Dispatch 至少包含 Task ID、Contract Version、Base SHA、Agent Profile、Worktree Mode、Required Environment、Allowed Scope 和 Required Gates。

Git Worktree 只隔离代码 checkout。共享数据库、缓存、端口、容器、账号或外部写入存在时，必须执行 PROVISION、VALIDATE、EXECUTE、CLEANUP。

## Evidence

Implementation Evidence 与 Acceptance Evidence 不能互相替代。Evidence 必须记录 task、contract_version、subject_sha、provenance、runner、environment、command_id、timestamp、exit_code、artifact_digest 和 source_uri。

Repo 只保存 manifest、摘要、digest 和引用；原始日志、截图、视频和大型报告保存为 CI Artifact。禁止提交 Secrets、生产凭据、完整生产日志或个人数据。

新 SHA 必须执行 Evidence Impact Analysis。R2/R3 的相关业务代码发生变化时，默认重跑完整 Required Verification。Reviewer 要求修改后的旧 Review Approval 失效。

## Integration

Execution 可以并行，Integration 必须串行。Worker 只提出 `proposed_state_changes`；Main 从最新目标分支建立 Integration Candidate，合入代码并同步已批准的项目事实，然后对同一个 Candidate SHA 做集成验证。

## State machine

主路径：

```text
CLARIFYING
DESIGNING
READY
IMPLEMENTING
VERIFYING
REVIEWING
ACCEPTING
INTEGRATION_PREPARING
INTEGRATION_VERIFYING
MERGE_READY
MERGED
POST_MERGE_VERIFYING
DEVELOPMENT_COMPLETE
```

异常状态：`BLOCKED`、`CHANGES_REQUESTED`、`CONTRACT_CHANGE`、`REASSESSING`、`CANCELLED`。

上线项目继续：`RELEASE_READY → ARTIFACT_BUILT → DEPLOYED → OBSERVING → STABLE`；异常为 `ROLLED_BACK` 或 `INCIDENT`。

## Governance changes

`AGENTS.md`、`governance/`、`.github/`、`.codex/` 与 `scripts/engineering/` 的实质修改必须使用独立 Governance Task、独立 Review、用户批准和 CI。任务记录 Governance commit 与 digest；合并前若相关制度变化则进入 REASSESSING。

Waiver 必须记录申请人、批准人、被跳过 Gate、原因、Task、期限、补偿措施和剩余风险。生产数据备份、不可逆迁移回滚方案、生产权限、Secret 保护及法律安全硬约束不可豁免。
