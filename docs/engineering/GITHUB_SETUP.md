# GitHub Setup

V1 使用个人账号下的 Public 仓库。

## Automated configuration

安装并登录 GitHub CLI 后运行：

```powershell
./scripts/engineering/configure-github.ps1 -Owner <github-user> -Repository codex-engineering-os
```

脚本创建：

- `product-approval` Environment
- `governance-approval` Environment
- `production` Environment
- `main` Ruleset
- Required status checks
- PR、严格更新、禁止 force push和禁止删除规则

这是单人仓库，因此 Environment 的 `prevent_self_review` 必须保持关闭。AI Reviewer 与 Verifier 的结论是 Evidence，不作为第二个 GitHub 人类账号。

GitHub REST API 不提供本项目所需的管理员绕过写入设置。首次配置时，仓库所有者必须依次打开仓库的 **Settings → Environments → product-approval / governance-approval / production**，在每个 Environment 中取消勾选 **Allow administrators to bypass configured protection rules**，然后保存保护规则。脚本会在完成其他自动配置后复核这三个 Environment；只要任意一个仍允许绕过，脚本就列出其名称并以非零状态退出，不会报告配置成功。

只读复核命令：

```powershell
@('product-approval', 'governance-approval', 'production') | ForEach-Object {
    gh api "repos/<github-user>/codex-engineering-os/environments/$_" --jq '"\(.name): can_admins_bypass=\(.can_admins_bypass)"'
}
```

三行结果都必须为 `can_admins_bypass=false`。

## CODEOWNERS

远程账号确认后，`.github/CODEOWNERS` 应将下列路径归属仓库所有者：

```text
/AGENTS.md
/governance/
/scripts/engineering/
/.github/
/.codex/
```

单人仓库不启用 required Code Owner review，否则由同一账号创建的 PR 可能无法自我批准。Governance 的强制人工门禁由 `governance-approval` Environment 提供。
