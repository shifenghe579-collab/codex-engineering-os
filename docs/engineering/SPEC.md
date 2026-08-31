# Confirmed Product Specification

以下是用户已经确认的规范性要求：

1. Agent 是临时执行资源，项目知识必须外部化到 Repo。
2. 系统固定五个 Agent 角色：Main、Explorer、Worker、Reviewer、Verifier。
3. 正确性以可复现 Evidence 为准，不以 Agent 自述为准。
4. Worker V1 使用用户创建的独立 Git Worktree 任务。
5. Execution 可以并行，Integration 必须串行。
6. 最终验证对象必须是包含代码与批准项目事实的 Integration Candidate SHA。
7. Governance 不能由 Main 自行修改并立即生效。
8. 使用个人 GitHub 账号和 Public 仓库，直接实现 GitHub-first 门禁。
