## Why

PR #327 的选中运行在 pending → running → paused 的自然转换中，进度更新但状态文字仍为“排队中”，甚至与暂停提示矛盾，未满足已有进度观察规格。

## 根因

`SelectedRun` 轮询关联任务，但状态文字只使用首次请求的 `run.status`；非终态变化不触发详情重取。暂停提示另行合并旧 run 状态，可能与新任务状态不一致。

## What Changes

- 选中运行状态及暂停提示优先使用当前关联任务快照，尚无任务快照时回退运行详情。
- 保留终态对账、停止轮询、账号/路由隔离及手动刷新行为。
- 增加不点击刷新按钮的状态转换浏览器回归，包括终态刷新和轮询停止。

## Capabilities

无新增或变更的规格要求；修复已有 `frontend/benchmark-management` 的进度观察隔离和终态对账要求，不新增 delta spec。

## Impact

仅修改 `frontend/src/benchmarks/RunHistory.tsx` 和现有浏览器验收脚本；不涉及接口、数据库或依赖变更。在用户指定的 `feat/322-benchmark-run-history` 分支工作。

## 复现与根因消除证据

2026-11-02 在 PR 原提交 `135b935` 上先新增测试，执行 `BENCHMARK_BASE_URL=http://127.0.0.1:5202 PLAYWRIGHT_MODULE=<本机 Playwright> CHROME_PATH=<本机 Chrome> node frontend/scripts/verify-benchmark-history.mjs`，退出码 1：等待“运行中”状态标签 6500ms 超时（脚本第 305 行），进度请求正常，失败对应旧状态文字。完整 RED 日志位于 `/tmp/pr327-status-red.log`。

修复后同一命令退出码 0，21 项浏览器检查通过，页面异常与未知请求均为 0。`RunHistory.tsx` 的状态文字与暂停提示均读取同一个当前状态，不再分别读取旧 run 状态或对旧暂停状态取 OR。终态对账路径与观察器隔离机制未变。GREEN 日志位于 `/tmp/pr327-status-green.log`。
