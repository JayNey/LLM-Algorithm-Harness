# 管理员按需沙箱诊断验证

变更 `add-on-demand-sandbox-diagnostics`，实现提交 `0ef3e3ec`。OpenSpec 任务 1/1 完成。[Issue #431](https://github.com/JayNey/LLM-Algorithm-Harness/issues/431)

## 验收结果

- 两页复用 `SandboxDiagnostic`，在管理员门禁内调用既有 `GET /api/v1/health/sandbox`，呈现未检查、检查中、正常、不可用及请求失败。诊断请求使用 45 秒超时，为最高 30 秒的配置探针和 Docker 启动检查留出余量。
- 在请求进行期间禁用按钮并拦截重复提交。组件卸载时取消请求。浏览器验证了延迟期间禁用、探针返回不可用、模拟网络超时与 HTTP 503 后就地重试。
- 首页刷新、系统页手动刷新和 30 秒自动刷新均沿用普通监控请求。诊断调用计数不增加，已取得的结果保留。
- 普通用户在首页和系统页均无操作。既有 FastAPI 测试核对匿名请求返回 401、普通用户直调诊断返回 403。
- 390px 视口的系统页文档宽度从 785px 降至视口内，组件健康表使用已有局部滚动容器。核对了两页 390px 的诊断截图。

## 验证命令

- `npm test` 通过 344 项。构建、Lint、格式和 Git 差异检查均通过。Vite 仍提示 CompareCharts 构建分块超过 500 kB。
- 本机 Chrome 使用 HTTP fixture 运行 `node scripts/verify-dashboard.mjs` 和 `node scripts/verify-settings.mjs all`，分别通过 30 和 20 项。浏览器用例使用模拟沙箱响应。
- `python3 -m pytest tests/test_api_monitoring.py tests/test_api_monitoring_probes.py -q --no-cov` 通过 93 项，测试输出包含依赖弃用警告。
- `comet classic openspec -- validate add-on-demand-sandbox-diagnostics --strict` 通过。

## 结论

PASS。已核对任务、增量规格、精简设计和最终实现。Tweak 的 `review_mode` 为 `off`，验证采用自动化检查和人工对照。
