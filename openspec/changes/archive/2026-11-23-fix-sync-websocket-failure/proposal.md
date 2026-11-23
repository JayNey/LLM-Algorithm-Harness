# 修复 WebSocket 同步连接失败降级

## Why

Issue #514：连接适配器在返回 handle 前同步调用 onError 时，观察器尚未登记当前连接，失败被身份守卫丢弃；连接工厂直接抛错也未被观察器处理。两种路径都会使页面停在 connecting，停止自动进度更新。

## What Changes

- 将同步 onError、连接工厂抛错与异步连接失败统一纳入降级处理。
- 在工厂调用前建立当前连接身份，处理 handle 尚未返回时的事件与清理顺序，忽略失效连接的后续事件。
- 保留现有 HTTP 轮询、有限重连、暂停、终态和 dispose 行为，补充确定性时序回归测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/evaluation-observer`：明确同步连接失败的降级、重连与资源清理验收。

## Impact

- 交付代码与测试限定为 frontend/src/evaluations/observer.ts、observer.test.ts；不改公共 API、依赖或后端。
- OpenSpec 产物使用简体中文；采用 tweak、direct 实施及缺陷回归，另保留真实 RED/GREEN 证据。
- 验证覆盖同步回调、构造抛错、异步失败、有限重连、恢复成功和 dispose；运行前端测试及可用的静态检查。
- 来源：https://github.com/JayNey/LLM-Algorithm-Harness/issues/514。
