# preserve-budget-difficulty-caps 验证报告

PASS。实施提交 `baf4e523`，任务 1/1。验证对象为 [议题 #391](https://github.com/JayNey/LLM-Algorithm-Harness/issues/391) 及 `frontend/budget-alerts` 的增量规格。

## 规格和实现

- 初始读取复用预算页的可取消资源读取。StrictMode 重跑时发出新的请求，加载期间和读取失败后表单尚不可用，失败时可重试。
- 只修改全局上限时，请求仅包含 `global_cap_usd`。服务端保留难度配置和超限动作。成功响应同时回填草稿和比较基线，随后刷新用量。
- 旧记录的 `difficulty_caps: null` 和正常空对象均可读取。显式清除一档时，按现有 PATCH 的整组替换约定发送剩余档位。
- 增量规格与精简 `design.md` 一致。Tweak 使用精简设计产物。自动代码审查按该变更的 `review_mode: off` 跳过，已逐项核对提交、增量场景和测试结果。

## 验证证据

- Chrome、Vite 开发模式、真实 FastAPI 和隔离 SQLite。修复前的 PATCH 实测多发了 `difficulty_caps: {}`。修复后 `frontend/scripts/verify-budget-settings-http.mjs` 通过六项检查，覆盖正常、延迟、失败重试、旧记录、空难度和清除单档。前三项均用 easy=1、medium=2 验证 PATCH、页面刷新和独立 API 回读。测试实例的 `AUTH_PROTECTED_RATE_LIMIT` 设为 1000，以容纳连续刷新。
- `npm test` 322 项通过，`npm run lint` 和 `npm run build` 通过。所有本次变更的前端文件通过 Prettier。
- `python3 -m pytest -q --no-cov tests/test_api_cost.py tests/test_budget_guard.py tests/test_budget_coverage.py` 42 项通过。worker 测试将全局上限提高到 0.04，确认仍由 easy=0.01 触发暂停或降级。
- `comet classic openspec -- validate preserve-budget-difficulty-caps --strict` 和 Git 空白检查通过。全局 Prettier 仍报告基线的 `frontend/scripts/verify-settings.mjs`，本机 Ruff formatter 仍报告基线的 `tests/test_api_cost.py` 未编辑区段。两处均已用实施前版本复现。
