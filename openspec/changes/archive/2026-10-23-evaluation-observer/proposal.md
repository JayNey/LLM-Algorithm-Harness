# Proposal: evaluation-observer（issue #225 T10 / 5.2，Step 1–3 观察器核心）

## Why

真实评估流程（#215）需要前端在详情页实时观察评估进度。现状：前端没有任何 WebSocket/轮询代码，进度只能在进入详情页时一次性读取。本 change 交付 #225 的观察器核心——可注入依赖的 `createProgressObserver`，覆盖 WS 订阅、HTTP 快照对账、受控降级轮询与全部生命周期边界；页面集成（Step 4）按与维护者协调的边界**等 #224 合入后另行 change**（已在 issue 留言声明）。

## What Changes

- 新增 `frontend/src/evaluations/observer.ts`：`createProgressObserver(deps): ProgressObserver`（deps 注入 fetchSnapshot/connectSocket/clock/onChange/recoverSession；start/refresh/invalidate/setVisible/setOnline/runMutation/dispose 生命周期），以及纯函数 `resolveProgressWsUrl(relative, location)`（http→ws、https→wss、绝对地址直通）。
- 新增 `frontend/src/evaluations/observer.test.ts`：node:test 注入假时钟/假 socket 的全边界测试（Step 1 先 RED，禁止真实 sleep）。
- delta spec：`frontend/evaluation-observer` 能力（进度观察生命周期需求与场景）。
- **明确不含**（递延至 #224 合入后的后续 change）：`useEvaluation.ts`、`EvaluationDetailPage.tsx` 改造、`verify-evaluations.mjs --scenario progress` 联测——即 #225 的 Step 4。

## Capabilities

### New Capabilities

- `frontend/evaluation-observer`：评估进度的 WS+HTTP 对账观察能力（订阅确认、事件合并、降级轮询、有限重连、终态收敛、权限/会话/可见性生命周期）。

### Modified Capabilities

- 无：不改既有 client 契约（`client.ts`/`types.ts` 零改动，HTTP 真值复用 `client.get(id)`——其返回与 WS `task.snapshot` 同形），不触 #224 的页面主战场。

## Impact

- 新文件仅 2 个（observer.ts / observer.test.ts），自动纳入 `npm test` 的 glob；测试文件被 `tsc -b` 排除，类型正确性由运行时与审查保证（仓库既定口径）。
- 不引入依赖（原生 WebSocket 由 React 适配器创建，核心不 import axios/WS）；不引入 Socket.IO（issue 明令禁止）。
- 后续集成 change（Step 4）将修改 `useEvaluation.ts`、`EvaluationDetailPage.tsx`、`verify-evaluations.mjs` 并补 `--scenario progress`。
