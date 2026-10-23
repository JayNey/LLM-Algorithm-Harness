## Why
现有 LLM 监控只有累计计数，无法回答最近统计窗口内的调用量、成功率与平均延迟。

## What Changes
- 现有管理员接口增加可选 window_seconds（1–86400），省略时保持累计统计。
- 保存有界、仅含数值的已完成调用记录，按完成时间聚合。
- 明确采集起点、保留范围、空窗口及不完整窗口语义，补充测试与文档。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/llm-call-metrics`: 增加窗口统计并允许持久化必要数值时间记录。

## Impact
监控存储、服务、现有路由、测试和 API 文档；无新增依赖。新增数值记录表，不修改认证数据。用户选择 2A：新分支，继续 tweak；窗口存储与现有 API 扩展按该选择执行。
