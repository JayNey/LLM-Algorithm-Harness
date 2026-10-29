## Why
个人题库导入后不能直接供实验、基准和 A/B 使用，必须手工准备服务器路径（#308）。需要统一引用和冻结执行数据以保障所有权与恢复一致性。
## What Changes
- 提供当前用户个人集合的 dataset_id；三类请求恰好接受 dataset_id 或 dataset_path 之一。
- 创建实验/A-B 或启动基准时冻结完整题目和来源标识；Worker 从持久化快照执行。
- 三类表单增加个人集合选择、保留原路径入口及现有模型/策略行为；补齐隔离、恢复与旧契约测试及文档。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/experiment-management`: 增加个人数据引用、所有者隔离、执行快照及表单选择要求。
## Impact
请求模型、文件服务列表、三个业务服务、三类前端表单/类型/校验、测试及运行文档。使用现有业务 config JSON，无数据库迁移或新增依赖。
## Workflow Decision
用户明确选择 1A2B：继续 tweak，创建独立分支。按单一 change 完成已说明的跨服务 API 与表单范围，预计超过六个文件；不升级 full。
