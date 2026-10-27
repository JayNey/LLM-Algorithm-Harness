# #232 真实评估端到端验收

## 范围与基线

本轮根据用户选择继续 `evaluation-live-evidence` tweak，在 PR #284 原分支 `tweak/20261026/evaluation-live-evidence` 补齐真实依赖和实际浏览器运行。原 PR head 为 `8797d07`；包含 #231 的 main `7efbecb`。新增 DeepSeek 官方 provider、Web 密钥选择及必要 WebSocket 运行依赖，HTTP 契约兼容扩展至 1.2.0；没有新增路由或数据库 schema。

用户明确授权现有 `config.json` 中供应商配置，本轮累计模型调用上限 US$0.10。真实运行使用代码 `9fab9b7`；后续提交 `2dd4188` 仅加强 live 脚本的 WS 生命周期/归属守卫；不改运行时 provider 代码。增强后的守卫通过纯自检及原始成功/失败 JSON 离线复核，未追加付费调用，历史真实证据源 SHA 保持原样。精简设计为 `openspec/changes/archive/2026-10-27-evaluation-live-evidence/design.md`，tweak 不要求独立 Superpowers Design Doc；两份 delta spec 采用完整验证。

## 实际执行事实

2026-10-27 在独立本地环境实际运行 API、认证/业务 SQLite、Redis、Celery solo worker、DeepSeek 和 Docker。专用账号通过真实 UI 注册/登录，Cookie HttpOnly 与 CSRF 检查通过；实际保存本人密钥、读取模型选项、单题单策略创建 201、启动 202。未替换任何业务 HTTP、WebSocket、队列、模型或沙箱，也未用 TestClient/in-process drain 充当 live。

最终浏览器运行 `run-20261027091524702.json` 通过，模型 `deepseek-flash`、vanilla、公开合成加法题，持久化记录 1/1 成功、179 tokens、应用估算 US$0.0000681。真实 WS 收到 `task.snapshot/subscribed/task.started/problem.completed/task.progress/task.completed`，URL 无 token；HTTP 最终快照 completed、100%。独立 AsyncTask/Celery 关联和开始/结束时间均匹配。`run_id=null` 如实记录为未关联，没有混用 ID。

两轮真实生成累计应用估算 US$0.0001362，worker 日志有两次官方生成 POST 200，账号日/月尝试计数均为 2，应用缓存关闭。按官方高峰 cache-miss 单价及实际 prompt 616 bytes+256 余量，双次保守上界 US$0.0053232；生成上限 2000 tokens，关闭 thinking，SDK 重试为 0。该金额不是供应商账单；未来复现须重新核对价格和授权。

第一次付费运行模型/沙箱已经成功，但 Uvicorn 缺 WebSocket 依赖导致 upgrade 失败；公开证据保留 `pass=false`，不删除失败或将轮询记录冒充实时事件。新增 `websockets`、重启隔离 API，并增加调用前真实握手后复测通过。更早的注册按钮探测失败未提交账号、未生成调用。

## 规格映射

- DeepSeek 官方 endpoint/凭证边界：`src/llm_client.py` 固定地址并拒绝非官方 override，禁 SDK 重试，支持专用环境 key；`api/auth/models.py` 拒绝任意 endpoint 与非 literal key。客户端及认证回归覆盖官方地址、环境覆盖、鉴权隔离、限时与脱敏。
- 实际模型枚举/验证：`api/auth/service.py` 和 `evaluation_options_service.py` 复用归属重核、5 秒 SDK 限时、关闭客户端和总调度预算；SDK 非分页结果 complete=true。参数化测试及真实模型选项/启动验证覆盖。
- 真实评估生成：SDK 的 DeepSeek thinking 字段按官方协议映射；Web 使用 30 秒生成限时、缓存关闭、用户计量。真实 worker→模型→Docker→持久化→页面和 WS 证明成功场景。
- 密钥列表与添加：前端 provider 类型、解析与分组加入 DeepSeek，保留旧场景；Node 测试和真实创建/列表流程通过，无密钥值留在公开证据中。
- 输入枚举扩展：冻结 OpenAPI 基线只在 `KeyCreate.provider` 加入 `deepseek`，保留严格兼容比较；旧输入值和其他组件不改。契约版本由 1.1.0 升为 1.2.0，目录静态断言同步新值。

## 验证状态

- 全量 `pytest -m "not online"`：3376 passed、11 skipped、128 warnings，退出 0；总覆盖率 92.67%，src 91.35%（门槛 90%）、API 94.86%（门槛 81%）。此前受限沙箱的 nginx 端口绑定 EPERM 已在允许本地端口的环境重跑解决，没有绕过或删除测试。
- 前端 `npm test`：258 passed；lint 退出 0（既有 BenchmarkDetail 两条 hook warning）；`tsc -b`、build 退出 0（既有大 chunk 提示）。最终 live 脚本 ESLint 及 16 项守卫自检通过。
- 149 项原有浏览器 fixture + 216 项外观矩阵断言通过；其 HTTP/WS 替换与 live 分开，断言摘要单独保存。
- ruff、black、src mypy（98 文件）、本次 API mypy（3 文件）、OpenSpec strict validate 和 diff check 通过。
- DeepSeek 客户端/前端解析先 RED 后 GREEN；全套相关 177 项 Python 测试通过。完整回归最初暴露静态目录期望与冻结输入枚举差异，按兼容扩展定向修正，未降低门禁。
- 最终审查提出一个 IMPORTANT：仅 snapshot/subscribed 不足以证明实时事件。已补同一评估生命周期事件断言及跨评估过滤，先失败后通过；原失败/成功 live JSON 分别得 false/true。同一独立 reviewer 定向复核通过，剩余 Critical/Important/Minor 均为 0。

## 证据与限制

入口及复现、清理命令见 [EVALUATIONS_QA.md](../../frontend/EVALUATIONS_QA.md)。公开证据目录为 `docs/frontend/assets/evaluations/live/`：保留失败/成功 JSON、遮盖后的结果截图、环境计量、验证命令和完整性索引。截图已实际查看，未见账号、原始 ID 或密钥。

本次使用 macOS Chrome、SQLite、单 worker、一个公共题目和一个供应商；未声称 PostgreSQL、生产部署、多 worker、多模型、移动端真实生成或余额耗尽等故障注入通过。原始凭证、Cookie、认证配置、数据库、worker 原始日志仅在本机受限临时目录；公开文件使用状态、哈希 ID 和聚合计量。既有 worker 还会在 `data/tasks/<evaluation_id>/` 写 TaskService 记录，绕过 API 的 TASK_SERVICE_ROOT；本轮只移动按状态确认归属的两个未跟踪记录到私有目录，不改动其他文件。保留 Cookie/CSRF、用户隔离和既有外壳；没有改外观实现。

本项是 #232 的小规模真实 smoke，不能代替 #231 工程质量或 #233 总体验收，也不自动关闭 issue。归档和推送仍按用户最终交付选择处理。

## 验收结论

完整性：5/5 tasks、5 个 delta requirements 和全部 11 个场景均有实现与测试/真实证据映射。正确性：测试、真实依赖、预算与隐私边界通过。设计一致性：符合精简 design；无未处理规格漂移，独立设计文档按 tweak 预设不适用。最终集成审查修复后通过。`comet guard` 和归档状态按后续公开 CLI 记录，未获得最终归档选择前不执行归档或推送。
