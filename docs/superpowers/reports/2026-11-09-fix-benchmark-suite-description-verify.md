# 基准套件编辑验证

- Issue [#426](https://github.com/JayNey/LLM-Algorithm-Harness/issues/426)
- 变更 `fix-benchmark-suite-description`，实现提交 `6ed60fe2`
- OpenSpec 任务 1/1 完成，增量规格通过严格校验

## 验收证据

- 描述省略时，更新题目后的 PATCH 回执保留原描述。提交 `null` 和新文本时，PATCH 回执与独立 GET 均返回相应值。覆盖由 `tests/test_api_experiment_benchmark.py` 提供。修复前回执为 `api suite`，修复后通过。
- 使用 Chrome、Vite、真实 FastAPI 与隔离 SQLite，从详情页清空已有描述。请求体包含 `description: null`，PATCH 回执与独立 GET 返回 `null`。当前页和禁用缓存后的刷新均显示默认描述提示。
- 浏览器验证页面内冻结及首次加载已冻结套件，两者均隐藏编辑和保存入口。直接提交修改描述并尝试解除冻结的 PATCH 返回 400。修复前首次加载已冻结套件时可见编辑按钮。
- 原有创建、列表、所有权、运行和学习曲线场景由现有 API 测试覆盖。代码对照确认保存后仍从服务端重新读取套件详情，服务层继续检查持久化的冻结状态。

## 命令结果

- `python3 -m pytest --no-cov -q --tb=short tests/test_api_experiment_benchmark.py`，66 项通过。
- `npm test`，341 项通过。`npm run build` 和 Python wheel 构建通过。
- 定向 Black、Ruff、Prettier、ESLint 与 `git diff --check` 通过。
- `comet classic openspec -- validate fix-benchmark-suite-description --strict` 通过。
- 归档后的主规格通过常规校验。严格校验仍提示主规格原有的 `Purpose` 占位文字。

## 全量离线测试

首次执行时，沙箱限制了真实 HTTP 用例的回环端口绑定。开放本机回环后，`python3 -m pytest -m 'not online'` 通过 4,063 项，跳过 18 项，覆盖率 93.46%。宿主预装的 Anthropic 1.5.0 超出项目约束 `anthropic>=0.18.0,<1`，在初始化 SDK 时拒绝测试使用的 HTTP 客户端。受影响用例如下。

- `test_self_consistency_controls_candidate_count_at_sdk_boundary[anthropic]`
- `test_few_shot_controls_retrieval_without_leaking[anthropic]`
- `test_reflexion_controls_context_on_generation_and_reflection[anthropic]`
- `test_cache_uses_provider_params_but_not_strategy_controls[anthropic]`

从独立依赖目录加载 Anthropic 0.125.0 后重跑 `tests/test_strategy_provider_params.py`，12 项全部通过。宿主依赖保持原安装状态。

## 结论

PASS。#426 的验收场景均通过。

按 tweak 预设，`review_mode: off`，因此由本次验证对照实现、精简设计与增量规格。运行环境为 macOS 上的 Chrome 和 SQLite。
