## Why

当前结构化日志以 JSON 逐行直出 stdout，一次评测在终端产生数十行机器格式输出，混在最终结果之前，可读性差；openai/httpx 的 "HTTP Request: ..." 重试信息也一并刷屏。机器可读的 JSON 流对管道与归档仍有价值，需要保留入口。

## What Changes

- 控制台默认输出人类可读的紧凑日志（ConsoleRenderer：短时间戳、键值对、必要颜色）。
- 新增 CLI 参数 `--log-format {console,json}`，默认 `console`；`json` 保留现有机器可读行为。
- 将第三方噪音日志源（httpx、httpcore、openai）压到 WARNING，重试等异常仍经 harness 自身事件呈现。
- 脱敏处理器在两种格式下均保持生效。

## Capabilities

### New Capabilities

- `console-output`: 定义评测日志的终端呈现：默认人类可读、JSON 显式可选、第三方噪音压制与双格式一致脱敏。

## Impact

- 影响 `src/utils/logging.py` 与 `src/main.py` 的 CLI 参数。
- 不改变日志事件集合、脱敏规则与结果落盘格式。
