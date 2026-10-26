## Why
空间分析器始终返回占位结果，现有 profiler 在父进程使用 tracemalloc，无法反映候选代码实际分配。

## What Changes
- 在现有 host/Docker 执行边界内部采样 Python 分配峰值，接通 Problem 上下文。
- 汇总公开测试峰值并按沙箱预算计算空间效率，失败不生成伪造分数。
- 补齐真实执行回归测试及采样、评分限制文档。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
无。本次修复既有空间评估实现，保持现有结果字段和执行协议；skip_specs 为 true。

## Impact
涉及 sandbox_executor、空间分析器及其编排、相关测试和代码质量使用说明；不新增依赖。
