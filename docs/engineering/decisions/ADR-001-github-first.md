# ADR-001: GitHub-first V1

- Status: Accepted
- Date: 2026-08-31

## Context

纯本地脚本只能发现违规，无法可靠阻止不满足条件的变更被合并。用户选择个人 GitHub 账号和 Public 仓库。

## Decision

V1 以 GitHub Pull Request、Actions、Ruleset、Actions Artifact 与 Environment 为集成和门禁基础。本地不实现独立调度服务。

## Consequences

- 必须维护 GitHub Workflow 与保护配置。
- AI Reviewer/Verifier 结果作为 Evidence，不冒充独立 GitHub 人类身份。
- 单人仓库的用户批准使用受保护 Environment；不能启用阻止唯一用户自审的配置。
