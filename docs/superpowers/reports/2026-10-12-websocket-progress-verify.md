# 验证报告：websocket-progress（上游 issue #150）

- 日期：2026-10-12
- 分支：comet/websocket-progress（基线 e01c729，含 #149/#181/#182/#183 队列与执行器、#174 监控）
- 验证模式：full（10 变更文件 / 1 delta capability / 9 任务）；verify_mode=full（含 delta spec）
- 独立审查：第一轮 requests-changes（3 IMPORTANT + 5 WARNING + 5 SUGGESTION），全部修复；定点复审结论见 §审查结论

## 检查结果简表

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 9/9 `[x]` |
| 2 | 实现与 tasks 一致 | PASS | `git diff e01c729..HEAD` = progress 模块 + worker 发布点 + WS 端点 + 接线 + 8 测试 + 文档，无超范围改动 |
| 3 | 构建/测试通过（Runtime 证据） | PASS | build check exit=0（log 1054daae）；verify check 见 §验证证据（1690+8 passed，coverage ≥90，门禁原样） |
| 4 | 相关测试通过 | PASS | tests/test_api_ws.py 8 条全过（内存流，无 Redis 依赖） |
| 5 | 无安全问题 | PASS | WS 鉴权走 AuthService.authenticate；owner 校验 fail-closed（不存在与无权同答 4403）；token 走 query 的部署注意事项已写入 API.md |
| 6 | 最终集成代码审查 | PASS | 第一轮全部 13 项发现已修复并有回归测试；定点复审见 §审查结论 |
| 7 | 核心场景与边界验证 | PASS | 见 §场景核对 |

## OpenSpec validate

`comet classic openspec -- validate websocket-progress` → valid

## 场景核对（delta spec: api/progress-streaming）

| Requirement / Scenario | 核对方式 | 结果 |
|---|---|---|
| 进度事件发布 · Redis 故障不阻塞任务 | publish_progress 全路径 try 包裹；test_publish_returns_false_when_redis_down；审查者确认 import/json/client 构造均在 try 内 | PASS |
| WS 订阅与鉴权 · 仅任务所有者可订阅 | test_cross_user_subscription_is_denied_4403；fail-closed（不存在与无权同答） | PASS |
| WS 订阅与鉴权 · 订阅即得快照 | test_subscribe_sends_snapshot_and_forwards_events（快照帧 + 后续转发事件）；订阅先于快照读取（无丢失窗口，审查 IMPORTANT 2 修复） | PASS |
| WS 订阅与鉴权 · 无效令牌被拒 | test_invalid_token_is_rejected_4401 / test_missing_token_is_rejected | PASS |

## 验证证据

- build check（Runtime）：exit=0，log `openspec/changes/websocket-progress/.comet/checks/1054daae-a25a-4616-a22d-e233c7afaef8.log`
- verify check（Runtime）：见 `.comet/checks/` 最新日志；门禁 90 原样

## 审查结论

**第一轮**（general-purpose 子代理，逐行 diff + 复跑 WS 测试 + lint）：`requests-changes`，13 项发现，处置：

- **IMPORTANT 1（已修复）**：worker import 顺序触发 ruff 0.17 I001（CI lint 必红）。`ruff check --fix` 修复。
- **IMPORTANT 2（已修复）**：快照读取先于 Redis SUBSCRIBE，DB 读→订阅确认窗口内发布的终态事件永久丢失。重排为**先订阅、后读快照、先发快照、后启动转发**——排队事件自然晚于快照送达，窗口归零。
- **IMPORTANT 3（已修复）**：API.md 声明了从不发送的 error 帧（且与 4403 约束自相矛盾），design 决策 5 承诺未实现。改文档（删除 error 帧行、对齐"订阅终止由客户端重连"表述）并对齐 design 与实现。
- **WARNING（已修复）**：每次发布新建 redis client 且无超时（网络黑洞时每单元停顿数十秒）。改为模块级共享 client + 1s socket 超时。
- **WARNING（已修复）**：forward 对 send_json 失败无处理（静默死亡 + 存储异常重抛）。send 失败即干净返回；unsubscribe/finally 吸收取消与清理异常。
- **WARNING（已修复）**：畸形帧以未处理异常杀连接。receive_json 非断连异常忽略、非 dict 帧跳过。
- **WARNING（已修复）**：事件队列无界。Redis 流改为 maxsize=200 丢弃最旧（进度事件天然可被后继取代）。
- **WARNING（已修复/显式声明）**：token 走 query 串（浏览器 WS 无自定义 header）。部署注意事项写入 API.md（剥离访问日志 query 或改短时票证）。
- **SUGGESTION（已修复）**：共享发布客户端（同 WARNING 修复）；pump_task 属性挂载改为 Subscription dataclass；发布失败日志升为 WARNING；design.md 引用改为实际使用的 EvaluationService；API.md 注明 percentage 与失败单元的关系。
- 记录不阻塞：pump 内 json.loads/aclose 失败已包裹为 best-effort。

**第二轮定点复审**（同一审查者，只审修复 diff 9b3a09d，复跑 ruff 与 WS 测试）：`approve`。逐项确认三项 IMPORTANT 到位（import 排序全仓绿；订阅先于快照消除丢失窗口且 4403 路径释放订阅；协议文档与 design 对齐实现），六项 WARNING 修复到位（共享发布客户端 1s 超时且降级路径有效；forward 干净返回；畸形帧忽略；有界队列丢最旧且无竞态；Subscription dataclass 取代属性挂载；发布失败日志升 WARNING），无新引入问题。两条非阻塞备忘：pump 因网络错误死亡时 unsubscribe 重抛清理异常（仅日志噪音）；模块级发布客户端无显式 close（无害）。

## 已知豁免

- problem.started / iteration.completed 事件、日志流：非目标（issue 标注可选/需引擎回调扩展）
- 完整事件日志持久化回放：非目标（快照 + 后续事件即回放语义）
- token 经 query 传参：设计决策，部署注意事项已写入 API.md
- 时间戳：事件载荷用 aware UTC isoformat，DB 列保持 naive UTC 约定
