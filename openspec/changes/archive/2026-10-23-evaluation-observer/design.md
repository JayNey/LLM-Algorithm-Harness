# Design: evaluation-observer

> 范围声明：本 change = #225 的 Step 1–3（观察器核心）。Step 4（`useEvaluation.ts`/`EvaluationDetailPage.tsx` 集成、`verify-evaluations.mjs --scenario progress` 联测）按 issue 留言声明的边界，等 #224 合入 main 后另行 change。

## 现状盘点（main 6365a64）

- `EvaluationClient`（client.ts/types.ts）无任何 WS/进度方法；`get(id)` 返回完整 `Evaluation`（含 `status`/`execution_progress`/`progress`），与 WS `task.snapshot.data`（`EvaluationResponse.model_dump()`）同形 → **HTTP 真值直接复用 `get(id)`，零改 client.ts**，避开与 #224 的共享冲突面。后端另有轻量 `GET /evaluations/{id}/progress`（仅 ProgressInfo、无 status，判不了终态），不采用。
- WS 契约（api/routes/ws.py，已亲自核对）：Cookie 认证（`harness_access_token`），URL query token 可选；accept 后发 `{"type":"connected"}`；subscribe（`{"action":"subscribe","task_id":<evaluation_id>}`，字段名历史遗留但值就是 evaluation_id）→ 先 `task.snapshot` 后 `subscribed`；4403 = 不存在或非本人（无存在性 oracle）；4401 = 认证失败；畸形帧服务端忽略。
- 前端测试栈：`node --test` + `node:assert/strict` + strip-types，import 带 `.ts` 后缀，无 fake timer/WS mock 先例（本 change 自建）；测试文件被 `tsc -b` 排除，经 package.json test glob 自动纳入。
- 401 处理与 Cookie 刷新全在 `auth/http.ts`（单飞刷新 + 重试一次）；observer 不重做，只消费结果。

## API 形状

```ts
export const OBSERVER_TIMING = {
  subscribeTimeoutMs: 5_000, // subscribe 后 5s 未收到 subscribed 帧 → 失败
  mergeWindowMs: 2_000, // 事件合并窗口：窗口内多事件只触发一次刷新
  staleLiveMs: 15_000, // live 下 15s 无任何事件且非终态 → 主动刷新一次（丢事件/漏终态兜底）
  degradedPollMs: 3_000, // 非 live 模式的 HTTP 轮询间隔
  reconnectBackoffMs: [3_000, 6_000, 12_000, 30_000], // 第 n 次重连前等待，越界取末值
  maxReconnects: 5, // 超过后放弃 WS，保持降级轮询
  rateLimitMs: 30_000, // 429 后至少 30s 不发任何请求
} as const;

interface ObserverDeps {
  fetchSnapshot(id: string, signal: AbortSignal): Promise<Evaluation>; // HTTP 真值
  connectSocket(handlers: SocketHandlers): SocketHandle; // 原生 WS 仅在 React 适配器创建
  clock: {
    now(): number;
    setTimeout(fn: () => void, ms: number): unknown;
    clearTimeout(h: unknown): void;
  };
  onChange(event: ObserverEvent): void;
  recoverSession(): Promise<boolean>; // 4401/401 时复用既有刷新；true=可重试
}
interface ProgressObserver {
  start(evaluationId: string): void;
  refresh(): void; // 手动刷新；与自动刷新共享非重叠约束
  invalidate(): void; // 外部失效（等价一个事件）
  setVisible(visible: boolean): void;
  setOnline(online: boolean): void;
  runMutation(fn: () => Promise<void>): Promise<void>; // epoch++，包住启动/取消
  dispose(): void;
}
type ObserverEvent =
  | { type: "snapshot"; evaluation: Evaluation; mode: ObserverMode }
  | { type: "mode"; mode: ObserverMode } // live|degraded|stopped
  | { type: "error"; message: string; mode: ObserverMode } // 瞬时失败（网络/5xx），观察继续
  | { type: "forbidden" } // 4403/403/404：清数据并停止
  | { type: "unauthorized" } // 401/4401 且恢复失败：停止，适配器负责回跳
  | { type: "settled"; evaluation: Evaluation }; // 终态/paused：自动观察已停止
export function resolveProgressWsUrl(
  url: string,
  loc: { protocol: string },
): string;
```

## 时序语义（测试与实现共守）

- **模式机**：`idle → live ⇄ degraded → stopped`；另有内部 `paused`（隐藏/离线时冻结一切定时器并关闭 socket，恢复时立即刷新一次并重连，重连计数清零）。
- **启动**：`start(id)` → 幂等（同 id 重复 start 忽略；换 id 先 dispose 旧资源）→ 立即 HTTP 刷新 → connectSocket → 发 subscribe 并起 5s 确认定时器。收到 `subscribed` 前收到的 `task.snapshot` 也按事件处理（invalidate）。
- **事件规则**：除 `connected`/`subscribed`/`pong` 外一切服务端帧都只做一件事——invalidate（"事件仅失效"，绝不直接改状态）。invalidate 在合并窗口内置一次 pending 标志；窗口到期至多发起一次刷新（"pending 一次失效"）。
- **非重叠请求**：任意时刻至多一个 in-flight `fetchSnapshot`；in-flight 期间到达的失效只置 pending，完成后若 pending 则立即再刷一次（仍是单周期）。
- **HTTP 真值**：只有 `fetchSnapshot` 的结果进 `onChange({type:'snapshot'})`；应用前检查 `signal.aborted` 与 epoch。
- **终态收敛**：快照 `status ∈ {completed, failed, cancelled, paused}` → 发 `settled`、关 socket（先发 unsubscribe）、清定时器、mode=stopped。这是"漏终态"的兜底：live 15s 无事件主动刷一次、degraded 每 3s 轮询，两者都保证最终经 HTTP 真值收敛。
- **重连**：WS 失败（error/close 非 4401/4403、subscribe 超时）→ 按退避序列 3/6/12/30s 计划重连；成功后计数清零；累计 5 次失败后放弃 WS（保持 degraded 轮询）。重连成功重新 subscribe。
- **429**：任何响应 429 → rateLimitUntil = now+30s，期间不发起请求、定时器顺延。
- **其他请求失败**（网络/5xx）：`onChange({type:'error'})`，轮询按退避序列顺延，成功后复位。
- **权限**：WS 4403 或 HTTP 403/404 → `onChange({type:'forbidden'})`、清数据、停止，不重试（与后端"无存在性 oracle"对称）。
- **会话**：WS 4401 或 HTTP 401（http 层刷新重试已失败）→ `recoverSession()`；成功 → 立即重连/刷新（不计入重连失败），失败 → `onChange({type:'unauthorized'})` 停止，适配器负责失效回跳。
- **epoch**：`runMutation(fn)` 先 epoch++ 并 abort in-flight（启动/取消后旧观察周期作废），await fn() 后 invalidate。所有异步完成点检查 epoch 与 `signal.aborted`，过期结果丢弃。
- **WS URL**：`resolveProgressWsUrl` 仅处理相对路径（`http:`→`ws:`、`https:`→`wss:`），绝对 ws(s) 直通；React 适配器负责拼 `VITE_WS_URL` 并只在此处 `new WebSocket`（issue 要求 token 不进 URL——认证走 Cookie）。

## 测试策略

`observer.test.ts`（node:test，import 带 `.ts` 后缀）：手写 FakeClock（记录计划回调、可手动 advance）+ FakeSocket（记录发帧/关闭码，可手动注入服务端帧与 close）+ 调用记录数组；所有时序断言通过 `clock.advance()` 驱动，零真实 sleep。用例分组：URL 解析 / 启动与订阅确认 / 事件合并与非重叠 / 降级与重连退避 / 429 / 终态与漏事件收敛 / 4403 与 401 路径 / 隐藏离线暂停恢复 / epoch 与 dispose 清理。Step 1 先全量 RED（observer.ts 未实现），Step 3 实现转绿。

## 风险与回退

- 纯新增文件，不改任何既有模块；回退 = 删两文件。
- 与 #224 的冲突面仅剩"未来集成 change"，本 change 不触碰。
- 语义解释风险（如 15s 的确切含义）已在本文钉死；issue 原文未逐字定义的常数取上述解释，验收时以本 design 为契约，若维护者有异议按 PR 审查意见调整（常数集中一处，改动成本低）。

## Step 4 集成设计（#224 合入后补齐）

- `useEvaluationLive(client, evaluationId, owner, enabled)`：观察器的 React 适配。enabled = 详情数据处于非终态；原生 WebSocket 仅在此适配器创建（`resolveProgressWsUrl(readViteEnv().wsUrl, location)`，Cookie 认证无 token 参数）；`recoverSession` 以一次 `client.get` 探测（复用 HTTP 层 401 刷新重试），仍 401 返回 false → unauthorized → 页面清会话回跳。
- `EvaluationDetailPage`：非终态挂载观察器；快照数据直接进 `EvaluationFacts`（HTTP 真值）；连接/降级状态以 role=status 提示。
- 验证：`verify-evaluations.mjs --scenario progress`（routeWebSocket 假服务：snapshot+subscribed+task.progress；HTTP 真值递进 20%→60%；断言 WS URL 无 token、事件驱动刷新）。

## 已知限制（Step 4 验收备注）

- **paused 自愈**：观察器把 paused 视为 settled（停止观察）。T9 界面当前无「恢复运行」入口；若后续接入 resume，恢复后需手动刷新或由页面在操作成功后重新挂载观察器。属产品语义边界，非缺陷。
- **forbidden 静默停止**：4403 事件清数据并停止（无存在性 oracle），页面无独立提示，与后端「不区分不存在与无权限」口径一致。
