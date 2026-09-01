# Current Architecture

## V1 components

```text
Codex roles
    ↓
Versioned repository artifacts
    ↓
Python Gate Engine
    ↓
GitHub Actions required checks
    ↓
GitHub Ruleset and protected environments
```

Repo 是可审计组织记忆，不被假定为绝对真理。GitHub 是 V1 的集成与硬门禁平台；本地 Codex 负责需求控制、调查、实现、审查和验收工作流。

Gate Engine 只判断结构、来源、版本、风险下限和所需证据是否满足，不宣称判断产品语义或技术事实的真伪。

## Pull-request authorization freshness

有 `base-ref` 的 PR 校验以显式 base/head Git tree 为事实来源，不依赖当前 checkout。`MERGE_READY` 要求显式 base、implementation/candidate/Evidence 授权 SHA 与显式 head 形成完整祖先链；每个授权 SHA 之后只能追加同一 Task 的合同、Evidence 和 HANDOFF 记录，并冻结合同语义、治理基线、既有批准与记录。

Squash merge 后，`MERGED` 及后续生命周期 PR 不再要求 pre-squash 授权 SHA 属于 post-squash main。它们从显式 PR base 继承已接受的授权快照，只允许合法状态和 HANDOFF 更新；candidate、批准、Evidence 引用及 manifest 保持不变。缺失或 shallow Git 历史一律失败关闭。没有 `base-ref` 的仓库级校验继续读取当前工作树。

经上述显式 base/head 授权判定的生命周期 PR，不重复要求修改 Task 中已冻结的 `change_impact` 所声明的历史 SPEC、ARCHITECTURE、PROJECT 或 ADR 文档。该例外仅跳过“声明为 true 但本 PR 未修改对应文档”的出现性要求；范围、禁止/保护路径、反向 impact 一致性、合法转换、授权冻结和生命周期路径限制仍然执行。实质性 PR 继续完整执行双向 change-impact 检查。
