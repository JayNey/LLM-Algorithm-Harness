## Context

见 proposal。用户明确选择直接使用 PR #284 原分支 `tweak/20261026/evaluation-live-evidence`，并授权项目现有供应商配置、累计 US$0.10 模型调用预算。原 PR 无 Comet 状态文件，本轮已在原 change 补建并选择；不新建第二个 change。

## Goals / Non-Goals

**Goals:** 执行并记录真实浏览器→API→Redis/Celery→供应商→Docker 沙箱→结果链路，保留按层级的事实与失败证据。

**Non-Goals:** 不使用 Mock/route.fulfill/socket 替代，不取其他用户凭证，不扩大模型调用预算，不重设计前端或引入新 API。

用户进一步明确选择继续 tweak：为现有 DeepSeek 凭证增加受控支持，再真实联调。该变更跨 provider 类型、SDK、Web 输入与前端分组及相关测试，作为同一 change 完成；按完整模式验证规格与集成，不另起 change。既有 API 路由保持不变，只扩展受支持的 provider 值。

## Decisions

- 本地 API/worker 使用相同隔离认证库、业务 SQLite、SECRET_KEY/ENCRYPTION_KEY；测试账号、密码、供应商 key 只保存在权限 0600 的本地文件，不输出或提交。CLI 既有 config 只作已授权配置来源，通过应用自身保存接口建立测试用户的 key。
- Redis 使用独立本地实例，Celery 使用真实消息与 worker；Docker daemon 和 python:3.11-slim 沙箱须完成实际运行预检。服务过程可复现，退出时仅清理本轮创建的资源。
- 从真实浏览器登录起，读取实际选项、一个公开合成题目与 vanilla 策略，设置小预算；禁止 route.fulfill、替换 WebSocket 或 TestClient/in-process drain。记录真实 201/202、ID 关联、HTTP/WS 观察、结果与 worker/模型/沙箱证据。
- 调用前核对模型价格、生成 token 上限与成本边界；单轮最小生成，累计不得超过 US$0.10；未知价格或无法限制时停止模型调用，明确阻塞，不自动扩大预算。
- 输出只允许状态、脱敏标识、时间、数值成本及公共合成题目结果；截图前移除账号身份与凭证字段，脚本异常不输出请求体或响应正文中的秘密。
- DeepSeek 使用独立 `deepseek` provider 和固定 `https://api.deepseek.com`，不把它伪装成 OpenAI；模型列表与验证复用现有归属、限时、禁 SDK 重试、关闭及脱敏逻辑。Web 不增加任意 base_url 输入；显式 DeepSeek provider 拒绝非官方 URL，既有 OpenAI 自定义地址行为保持。
- Web DeepSeek 生成使用 30 秒 timeout、关闭 thinking，避免简单单题在默认思考模式中耗尽输出或超时；模型枚举/连接检查仍由 SDK with_options 强制 5 秒。CLI 的 enable_thinking 映射为官方 `thinking.type`；既有 SiliconFlow 开关保持不变。
- 使用官方 2026-10-27 高峰 cache-miss 单价作保守上界：输入 $0.30/百万 token、输出 $1.20/百万 token。隔离账户每 UTC 日/月最多 2 次真实生成尝试，单次最多 2000 输出 token；调用前用实际 vanilla prompt UTF-8 字节数加协议余量计算输入上界，核对累计上界不超过授权预算。

## Risks / Trade-offs

- [依赖启动或外网调用失败] → 记录原始层级和脱敏错误，先调查再修复；不将健康检查或 fixture 成功记作 live。
- [供应商计费/额度不确定] → 已授权预算内只进行受限最小运行；不调用未授权凭证或追加预算。

## 联调发现的必要修复

新装 Uvicorn 不自带 WebSocket transport；真实模型/沙箱完成但 WS upgrade 返回 404。运行依赖增加 websockets，live 脚本在付费前验证真实 Cookie WebSocket。保留首次失败证据，最多一次受限 completed 重试并累计费用。新增 provider 输入枚举按兼容扩展定向更新 OpenAPI 基线，契约次版本为 1.2.0，不放宽门禁。

最终审查将 live 通过条件加强为同一评估在同一个真实 socket 上收到 snapshot/subscribed 与 started/problem.completed/completed；帧按评估 ID 过滤，公开只保留哈希关联。该纯守卫的负例和历史证据离线复核不追加生成调用。
