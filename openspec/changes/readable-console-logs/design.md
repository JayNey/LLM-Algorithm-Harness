## Context

`setup_logging` 固定使用 `JSONRenderer` 并经 `logging.basicConfig(stream=stdout)` 输出；`main.py` 调用时不传任何格式参数。httpx 等第三方 logger 未做级别压制。

## Goals / Non-Goals

**Goals:**

- 终端默认看到简洁可读的进度与结果日志。
- 机器可读 JSON 通过显式开关保留。
- 两种格式下脱敏行为一致。

**Non-Goals:**

- 不改变日志事件集合、级别语义或结果/报告的落盘格式。
- 不引入日志文件轮转等运维能力。

## Decisions

1. **渲染器按 `console_format` 参数切换。** `console` 使用 `structlog.ConsoleRenderer()`（彩色、短时间戳），`json` 沿用 `JSONRenderer()`；`redact_sensitive_event` 处理器位于渲染之前，两种格式均生效。
2. **第三方噪音在 logger 级别压制。** `httpx`、`httpcore`、`openai` 设为 WARNING，连接重试的原始刷屏让位于 harness 自身的事件（如 `llm_api_error`、`llm_generation_failed`）。
3. **CLI 显式开关优于环境变量。** `--log-format {console,json}` 默认 `console`，管道/CI 用户显式选 `json`。

## Risks / Trade-offs

- [依赖 JSON 输出的既有管道受影响] → 默认值变更属于行为变化，`--log-format json` 一键还原；README 同步说明。
- [ConsoleRenderer 颜色码进入非 TTY 输出] → structlog ConsoleRenderer 在非 TTY 下自动降级为纯文本键值行。
