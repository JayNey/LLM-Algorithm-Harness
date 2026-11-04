## Why

Issue #336 指出 function 模式缺少返回结果 marker 时仍接受 stdout JSON，候选函数打印期望值后 SystemExit(0) 可被误判通过，污染评测结果。

## What Changes

- 显式传入 result_marker 时必须匹配该 marker 且 JSON payload 合法，否则返回 runtime_error。
- 仅未请求显式 marker 的 legacy 调用保留 stdout JSON 回退。
- 覆盖 Host、Docker、调试输出、非法 payload 和 stdin/stdout 兼容性。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `execution-protocol`: 强化已有“函数结果与调试输出隔离”要求（既有定义位于尚未归档的 execution-protocol change）。

## Impact

仅涉及 src/sandbox_executor.py 及其测试；无 public API、依赖或数据库变更。真实 Docker 验证需可用 daemon 和 Python 镜像。
