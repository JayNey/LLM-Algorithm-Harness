---
comet_change: fix-sync-websocket-failure
---

# 验证报告：fix-sync-websocket-failure

## 结论

通过。Issue #514 的同步连接失败已纳入现有 degraded 轮询与有限重连路径；直接构造抛错不再逃逸启动调用。验证对象为独立 worktree 的当前候选，仅包含 observer.ts 与 observer.test.ts 两个交付文件和本 change 的材料。

| 维度 | 结果 |
| --- | --- |
| 完整性 | 4/4 任务完成，1/1 MODIFIED requirement 已实现 |
| 正确性 | 6/6 delta 场景已映射实现和确定性回归 |
| 一致性 | 实现遵循身份先建立、回调暂存、异常统一降级及失效后清理的设计；沿用依赖注入和假时钟模式 |

## 实现与场景映射

- 连接身份在工厂前登记，Connection.handle 显式可空；初始化事件等句柄返回后按顺序处理（observer.ts:354–435）。工厂抛错时清空初始化事件并复用 onError，避免无句柄时重放 open。
- onError 先标记 closed、解除 conn，再关闭句柄与处理失败（observer.ts:399–405）；teardownSocket 采用相同失效优先顺序，关闭回调重入不会污染新连接。降级通知中发生 dispose 或 pause 后不再添加定时器（observer.ts:456–459）。
- 订阅超时进入退避：原有“5 秒未确认订阅按失败关闭”测试通过，继续验证超时关闭、3 秒轮询和首次重连。
- 漏终态经 HTTP 收敛：原有“终态经 HTTP 真值收敛”与“paused 快照同样停止自动观察”通过，原有 15 秒 live 兜底测试通过。
- 初始化同步报告失败：新增 sync-error 测试（observer.test.ts:415），验证 degraded、轮询、失败句柄关闭与 3/6/12/30 秒退避。
- 连接构造抛错：新增 throw 测试与“同步通知后构造抛错只安排一次失败退避”（observer.test.ts:560），验证启动不抛错、降级和失败计数上限。
- 失败通知去重与恢复：“同步失败的旧事件不影响后续连接恢复 live”（observer.test.ts:474）验证重复错误、关闭、打开、消息被忽略，重连成功停止降级轮询，成功后的失败重新从 3 秒退避开始。
- 同步失败后卸载：三种失败模式均验证 dispose 后无剩余定时器、请求、连接、回调或订阅帧；“同步失败降级通知中 dispose 不遗留定时器”（observer.test.ts:581）补充重入卸载。
- 补充边界：“初始化同步 open 和 subscribed 在句柄可用后有序处理”及“初始化同步 open 后 error 清理订阅定时器，close 回调不重复计失败”通过。

## 检查与证据

所有前端命令的 cwd 为当前 worktree 的 frontend 目录；Git 和 OpenSpec 命令的 cwd 为当前 worktree 根目录。

| 检查 | 实际结果 | 日志 |
| --- | --- | --- |
| node --experimental-strip-types --test src/evaluations/observer.test.ts（修复前） | 27 passed，8 failed；新增失败与 issue 时序及清理缺口一致 | /tmp/issue-514-red.log |
| 同一观察器测试（修复后） | 35 passed，0 failed | 平台命令输出 |
| npm test（最终候选） | 365 passed，0 failed，0 skipped | /tmp/issue-514-frontend-tests.log |
| npm run lint | 通过，0 errors | /tmp/issue-514-lint.log |
| npm run build | TypeScript 与 Vite 构建通过 | /tmp/issue-514-build.log |
| npx prettier --check src/evaluations/observer.ts src/evaluations/observer.test.ts | 通过 | 平台命令输出 |
| git diff --check | 通过 | 平台命令输出 |
| comet classic openspec -- validate fix-sync-websocket-failure --strict | 通过 | 平台命令输出 |

检查 JSON：/tmp/issue-514-checks.json。Build 已提交同一候选的实际证据；Verify 复用有效结果，未为提交报告重复执行相同检查。

## 审查、风险与验证边界

- 当前 tweak 配置 buildMode=direct、tddMode=direct、reviewMode=off；额外保留了真实 RED/GREEN。独立 reviewer 按配置跳过，本报告由实现会话核对最终差异与规格，不称为独立审查。
- CRITICAL：0；WARNING：0；SUGGESTION：0。未发现规格或设计偏离，无接受的行为偏差。
- 构建有大 chunk 提示，未改动打包配置；这不影响本次构建成功与观察器修复。
- 测试覆盖依赖注入的状态与时序。未执行真实浏览器故障注入、生产连接或付费模型调用；这些不在本次验收要求内。
- 依赖安装首次因沙箱 DNS 失败，联网重试 npm ci --ignore-scripts --no-audit --no-fund 成功，未修改锁文件。
- OpenSpec 完整性、需求映射、场景覆盖、设计遵循与代码模式均已核对；没有未验证的必需验收项。可进入 Archive，归档和 Git 交付等待当前用户决定。
