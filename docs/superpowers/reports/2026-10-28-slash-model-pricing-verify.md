# slash-model-pricing 验证报告

结论：PASS。Issue #297 的实现和验证完成，等待用户确认归档与交付方式。

## 范围与完整性

- 分支：`codex/slash-model-pricing`；基线：`00e9699de6a09630373e169c94920559653584d2`。
- 实现提交：`48f249d`、`72f5d15`；2/2 tasks 完成，1 项修改 requirement、4/4 场景覆盖。
- 六个源码/测试文件符合 tasks 范围，其余为当前 change 的规划与 Comet 状态产物。
- 采用 full 验证；该 tweak 使用精简 design.md，不需要完整 Superpowers Design Doc 或 plan。

## 正确性与场景对应

- 覆盖生效且可追溯：`tests/test_api_cost.py::TestPricing::test_catalog_override_and_history` 和真实 HTTP 往返测试均验证追加两版、目录最新值及历史最新优先。
- 含斜杠模型的真实 HTTP 往返：`test_full_model_ids_round_trip_over_http` 在本机 TCP 上使用 uvicorn/httpx，保存 Qwen/Qwen2.5-7B-Instruct 并读取相同模型的目录与两条历史。
- 编码与历史路径不混淆：同一测试同时保存 gpt-4、多层路径、history 结尾、字面 %2F、对应真实斜杠、中文及 URL 特殊字符模型；编码和原始斜杠请求均读取精确对应历史。前端编码测试锁定保存/历史的相同编码路径及原始响应模型值。
- 扩展路径保留认证与校验：`test_full_model_id_auth_and_validation_over_http` 覆盖未认证 401、空模型、201 字符模型、零/负价格 400 和无非法历史；200 字符模型可正常保存。端点边界单测同时覆盖认证、无效 token、错误处理与请求校验。
- `api/routes/costs.py` 在历史路由和通用模型路径上采用 path 转换器；历史后缀明确且优先注册。服务层与存储未改写模型字符串，没有重复 URL 解码。
- OpenAPI 参数文档包含完整模型 ID、一次编码、字面 %2F、历史地址与代理转发约定；公开路径模板、operation ID、认证、字段及冻结 v1 基线保持兼容。

## 调试证据

- 修复前真实 HTTP 回归 2 failed：编码后的 Qwen 模型保存为 404，未认证请求也先返回路由 404。
- 修复后同组定价测试 4 passed。扩大回归发现两个辅助函数以 route.path 查询公开路径；改为 route.path_format 后，示例验证与端点清单仍完整，OpenAPI 基线无需更新。
- 初次沙箱运行无法绑定本机端口；授权运行后真实 HTTP RED/GREEN 得到验证，不以该环境错误代替业务失败证据。

## 最终验证命令

以下验证在最后实现提交后重跑，退出码均为 0：

- `python3 -m pytest tests/test_api_cost.py tests/test_api_versioning.py tests/test_api_documentation.py tests/unit/test_api_endpoints.py tests/test_pricing.py --no-cov -q`：906 passed。
- `npm --prefix frontend test`：275 passed。
- `npm --prefix frontend run build`：TypeScript 与 Vite 构建通过。

Build 阶段另已通过：

- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/issue297-wheel`。
- `black --check api/routes/costs.py tests/test_api_cost.py tests/test_api_documentation.py tests/unit/test_api_endpoints.py`。
- `ruff check api/routes/costs.py tests/test_api_cost.py tests/test_api_documentation.py tests/unit/test_api_endpoints.py`。
- 前端 `npm run lint`、修改文件 `prettier --check`、`git diff --check`。
- `comet classic openspec -- validate slash-model-pricing --strict`。

## 一致性与审查

实现遵循精简设计和 delta spec，无漂移。检查最终集成 diff 的路由顺序、模型值传递、认证、参数边界和测试覆盖，未发现正确性或安全问题。没有新增端点、依赖、数据库迁移或架构协调。`review_mode: off` 沿用 tweak 预设，未派发自动代码审查；构建、测试、安全边界与 spec 一致性验证均已执行。

现有 Pydantic 弃用提示、BenchmarkDetailPage 的两个 hook lint 警告、前端 chunk 体积提示记录为既有验证输出；本变更未触及相应代码，所有命令成功。反向代理需原样转发编码路径，已写入 API 文档；本次真实 HTTP 验证直接覆盖应用服务器。

CRITICAL：0；IMPORTANT：0；新增 WARNING/SUGGESTION：0。未提交内容仅为本次验证报告与 Comet 状态更新；无用户或其他 change 的未提交改动。归档前 `branch_status` 保持 pending，主 spec 尚未同步。
