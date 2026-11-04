## Why
修复 #340：共享 SandboxExecutor 的命令耗时实例字段会被并行任务覆盖，污染超时结论和记录。
## What Changes
- 使用每次调用独立的计时数据，成功、异常及内存分析均使用本次命令耗时。
- 保持清理不计入算法预算，保持 worker 并发。
- 增加确定性竞争、Harness 多 worker 与真实 Docker 回归。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
无；修复既有判题与超时语义的实现，不改变协议。
## Impact
仅沙箱执行器及回归测试；无公开 API、依赖、schema 或架构变化。
