# 设计：本地持久化任务服务

## Task model

`TaskRecord` 保存 run_id、状态、配置指纹、题库指纹、单位总数、完成数、取消标记、`TaskUnit` 列表和有序 `TaskEvent` 列表。每个单位由 strategy、problem_id 和 repeat_index 组成，结果保存为 JSON；API/GUI 可以直接消费这些 Pydantic 模型。

## Persistence

`TaskStore` 将每个任务写入 `output_dir/tasks/<run_id>.json`。写入先落到同目录随机临时文件、flush/fsync 后使用 `os.replace`，避免进程中断产生半个 JSON。配置使用脱敏后的规范 JSON 计算 SHA-256；题库文件或目录按稳定路径和内容计算 SHA-256。恢复时指纹不一致立即拒绝。

## Scheduling and cancellation

`TaskService.run` 使用 `ThreadPoolExecutor(max_workers=...)`，只从 queued 单位派发任务，并在每次单位状态变化后落盘和追加事件。主循环用短轮询观察外部取消请求；取消后不再派发 queued 单位，queued 标记 cancelled，在途单位标记 `cancelled + uncertain=true`。无法强制终止外部 API 调用，因此不承诺 exactly-once。

## Resume

恢复只重新排队 queued、running 或 uncertain/cancelled 单位，保留已确认 completed/failed 的终态和结果；重新运行前必须提供匹配的配置与题库指纹。CLI 暴露 `--run-id` 和 `--resume`，默认入口继续保留。
