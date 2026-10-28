## Context

前端已使用 encodeURIComponent；ASGI 服务器在路由前解码一次，单段路径转换器不能匹配解码后的斜杠。服务层按模型字符串精确存取，无需调整存储。

## Decisions

既有 GET `/api/v1/pricing/{model_id}/history` 和 POST `/api/v1/pricing/{model_id}` 使用 path 转换器，history 注册在通用模型路由之前。保留 OpenAPI 路径模板和 operation ID，服务层不重复 URL 解码；拒绝空模型 ID，保留 200 字符上限及正数价格校验。前端将编码集中到私有 URL 函数，保存和历史使用同一模型编码。

真实 HTTP 测试通过本机 TCP 上的 uvicorn 与 httpx 覆盖编码解码边界（含字面 `%2F`，避免 TestClient 自身解码掩盖问题）。同时覆盖普通模型、模型名以 history 结尾、多层路径、特殊字符、认证及校验。前端测试锁定一次编码与不改写模型名的契约。

## Risks / Trade-offs

- path 转换器匹配范围扩大：保留 history 的明确后缀与路由顺序，测试相近模型互不串历史。
- 某些反向代理可能拒绝编码斜杠：文档要求原样转发编码路径，应用层只解码一次。
- 本变更无需 Superpowers 深度设计文档；以本精简设计和 delta spec 为验证依据。

## 调查与验证证据

- RED：`python3 -m pytest tests/test_api_cost.py -k full_model_id --no-cov -q`，2 failed；真实 HTTP 的含斜杠保存返回 404，未认证请求也被路由挡在认证前。
- GREEN：改用 path 转换器并拒绝空 ID 后，`python3 -m pytest tests/test_api_cost.py -k Pricing --no-cov -q`，4 passed；覆盖普通模型、编码和字面斜杠、字面 %2F、中文特殊字符、history 后缀、200/201 字符边界、认证和价格校验。
- 首次沙箱测试因禁止本机端口绑定失败；在允许绑定临时本机端口的环境重跑，确认上述业务 RED/GREEN。
- 扩大回归发现两个测试辅助函数把含转换器的 route.path 当作公开模板；改用 route.path_format，保持端点枚举和示例验证完整，冻结 OpenAPI 基线不变。
- 后端相关回归 906 passed；前端全量 275 passed，lint 无错误、修改文件格式检查通过、前端构建和 Python wheel 构建成功。前端既有两个 BenchmarkDetailPage hook lint 警告及打包体积提示不影响本次验证。
- 实际实现与回归修改共 6 个文件（含上述两个辅助函数）；Comet 规划、状态与验证产物不计源码规模。未新增 capability、端点、schema 或跨层架构协调，无升级信号。
