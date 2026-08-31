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
