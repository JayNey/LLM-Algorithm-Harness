## 1. 任务模型与存储

- [x] 1.1 定义 TaskRecord、TaskUnit、TaskEvent 和稳定 run_id/单位身份
- [x] 1.2 实现原子 JSON 持久化、列表/查询和配置/题库指纹

## 2. 调度与生命周期

- [x] 2.1 实现有界并发、queued/running/completed/failed/cancelled 状态和结构化事件
- [x] 2.2 实现取消、在途 uncertain 标记、停止新派发和恢复语义
- [x] 2.3 让 CLI Harness 使用任务服务，并保留直接 Harness 调用兼容性

## 3. 验证

- [x] 3.1 增加并发上限、失败终态、取消、恢复和指纹拒绝测试
- [x] 3.2 运行全量测试、编译检查、OpenSpec 严格校验并完成本地代码审查
