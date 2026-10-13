## 1. 实验启动接口

- [x] 1.1 实验运行接口提交 `run_experiment_task` 并返回任务标识，实验保持 `pending`；用 API 测试验证，且不依赖进程内线程跑完
- [x] 1.2 API 重启不再把已入队的 `pending` 实验标成失败；没有任务的 `pending` 实验和 `running` 实验仍标成中断

## 2. 导入启动接口

- [x] 2.1 题目导入接口提交 `run_import_task`，返回任务标识和作业标识，且不使用 `BackgroundTasks`

## 3. 基准启动接口

- [x] 3.1 基准运行接口创建 `pending` 运行并提交 `run_benchmark_task`，返回任务标识
- [x] 3.2 API 重启不再把已入队的 `pending` 基准运行标成失败
