# 前端 CI 门禁验证

变更 `frontend-ci-gates`，实现提交 `33fb47a9`，对应 [#401](https://github.com/JayNey/LLM-Algorithm-Harness/issues/401)。

## 结论

- **完整性 PASS**。OpenSpec 任务完成 1/1，严格校验通过。此变更配置 CI 工具链，适用 `skip_specs`。
- **正确性 PASS**。PR 工作流声明两个可区分的检查。Node 24.22.2 下，`npm ci`、ESLint、322 项 Node 测试及 TypeScript 与 Vite 生产构建均通过。
- **一致性 PASS**。`actionlint` 1.7.12 与 `git diff --check` 通过。两个任务都从前端 lockfile 安装依赖。Chromium smoke 运行生产预览，复用前端 fixture，报告由 CI 上传。
- Comet 的 Tweak 状态为 `review_mode: off`，本次执行配置、安全和测试核对。修改前后的 npm 审计均为同样的 14 条既有告警。Vite 保留既有的包体积提示。

## 浏览器与失败传播

- 在 macOS 隔离副本中，使用 lockfile 的 Playwright 1.65.0 安装 Chromium，并用 Bash 执行从 CI YAML 提取的 smoke 步骤。直达路由通过 66 项断言，实验创建通过 10 项断言，两者的未声明 API 请求均为 0。
- 在临时副本加入一条故意失败的单测后，`npm test` 退出码为 1。向临时生产构建注入工作流容器宽度回归后，直达路由报告 16 项失败，CI smoke 步骤退出码为 1。移除注入后再次通过正向验证。
- 验证完成时尚无本次变更的 GitHub PR 运行记录。托管 Ubuntu runner 的浏览器依赖安装和 PR 检查状态需在 PR 创建后核对。
