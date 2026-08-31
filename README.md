# Codex Engineering OS

Codex Engineering OS 是一套放在 Git 仓库中的 AI 软件研发运行制度。它不假设任何 Agent 永远正确，而是通过角色分工、版本化任务合同、独立证据、GitHub Actions 和受保护的合并流程，限制单点错误直接进入最终产品。

Canonical repository: https://github.com/shifenghe579-collab/codex-engineering-os

## V1 范围

- 五个固定角色：Main、Explorer、Worker、Reviewer、Verifier
- GitHub-first，个人公开仓库
- Worker 使用独立 Git Worktree 任务
- YAML Task Contract 与 Evidence Manifest
- Python Gate Engine
- GitHub Actions Required Checks
- Governance 变更与业务变更分离

V1 不包含自动 Worktree 调度、多 Main、Web 控制台、数据库或自动生产部署。

## 快速验证

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

运行 Gate Engine 测试：

```powershell
python -m unittest discover -s scripts/engineering/tests -v
```

检查一个任务：

```powershell
python scripts/engineering/task-check.py docs/engineering/tasks/T001.yaml
```

完整制度见 [governance/WORKFLOW.md](governance/WORKFLOW.md)。
