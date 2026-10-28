## Context
个人导入集合存储于认证库 api_file_datasets；三类业务 config 已持久化为 JSON，执行器要求 JSON 文件路径。
## Goals / Non-Goals
完成 #308 验收；不扩展逐题 CRUD 或修改公共题库，不重写导入服务和模型/策略选项。
## Decisions
- GET /datasets 仅列出所属用户个人集合，dataset_id 由 owner 稳定派生，解析时与当前 owner 再校验。
- 三种请求共享排他校验，dataset_id/dataset_path 恰好一个，空字符串无效。旧路径仍受 DATA_ROOT 约束。
- 创建实验/A-B 或基准 run 时读取并序列化完整题目到业务 config.dataset_snapshot，包括 owner_id、dataset_id/原路径、sha256、count、schema_version。响应保留摘要，不返回完整题库。快照与业务记录同事务，无孤儿快照。
- 快照随业务记录保留/删除，不依赖上传 TTL。Worker 从业务数据库读取快照，检查 owner/hash，用本机 TemporaryDirectory 生成 JSON，退出作用域自动清理。暂停/恢复生成相同内容；旧存量无快照记录沿用路径。
- 表单复用数据源选择组件，个人集合来自真实接口，提供加载/失败重试/空集合指引，切换来源清除另一参数；保留模型/策略代码。
## Risks / Trade-offs
- config 增大：沿用个人集合容量限制；API 视图移除题目正文。
- Worker 强杀可能留下系统临时目录：部署 tmp 清理策略清除残留，不扫描运行中任务。
- 多主机需要共享业务数据库；快照无需共享 DATA_ROOT/UPLOAD_DIR，旧 dataset_path 请求仍要求 API 可访问源文件。
