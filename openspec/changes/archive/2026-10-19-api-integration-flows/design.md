## 实现方案
使用 TestClient 经真实 ASGI 中间件与路由，隔离 SQLite 认证和业务库、上传目录、输出及检查点。通过 HTTP 注册、登录、存密钥、上传题目、创建并启动任务。消息投递替身记录待执行任务，测试显式排空队列时调用真实 Celery task.run；保留任务编排、检查点、策略、结果入库、统计及报告生成。只替换 LLM 返回、沙箱执行、Celery/Redis 传输，并给外部响应固定用量。
实验使用真实 ExperimentRunner 与比较报告；队列执行后轮询 HTTP 终态。所有等待有界，并发使用 barrier 明确重叠。恢复在首单元沙箱返回时经 HTTP 请求暂停，产生真实 paused 检查点；应用重建后经 HTTP 恢复，验证仅运行剩余单元，结果与费用不重复。预算分别测试零预算与首单元费用触达预算，恢复后不得绕过原预算。

## 验证
新增集成套件、相关 API/worker 回归测试、ruff/black 及 Python 编译检查。报告记录外部依赖边界，不把离线测试等同于真实 broker/worker 测试。

## 首轮集成证据与确认范围
2026-10-19：新增 7 项测试，5 项通过、2 项业务流程失败。并发创建、用户暂停后的应用重启及检查点恢复、零预算和首单元超预算后的停止与重试均通过。

1. 上传链路：`FileService._process_job` → `FileStore.merge_dataset` 仅写认证库中的 `api_file_datasets`，评估任务 `_resolve_execution_context` 仅从业务库 `ProblemStore` 读取。仅经上传创建的 `uploaded-only` 导致失败，不应通过测试预填同一题目掩盖。
2. 实验链路：`execute_experiment` 构造 `ExperimentService(recover=False)`，其 `auth` 默认为 None，`_build_runner_config` 抛出 `authentication service is not configured`。真实 task 将失败状态写回数据库。

用户已于本轮明确选择继续 tweak 修复上述断点。修复必须保持上传题目的用户隔离，并保留已有公共题库兼容性；实验 worker 必须使用服务器配置的认证服务解析所属密钥。评估优先读取当前用户上传题目，同 ID 覆盖公共题库；没有用户题目时沿用公共题库。不会将私有上传写入全局题库。实验 worker 使用服务器配置的 AuthService。
