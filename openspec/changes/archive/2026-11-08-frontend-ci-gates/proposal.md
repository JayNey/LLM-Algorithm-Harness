## Why

[#401](https://github.com/JayNey/LLM-Algorithm-Harness/issues/401) 要求在 PR 上反馈前端回归。目前 CI 只检查 Python，#400 修复的浏览器 fixture 已合入。

## What Changes

- 在 PR CI 中增加独立的前端检查，运行 ESLint、Node 测试、TypeScript 检查和生产构建。
- 在 Chromium 中运行生产构建的直达路由和关键工作流 smoke，复用已有 fixture。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。改动范围为 CI 工具链。

## Impact

涉及 GitHub Actions 和前端开发依赖。浏览器验证使用 fixture 响应。
