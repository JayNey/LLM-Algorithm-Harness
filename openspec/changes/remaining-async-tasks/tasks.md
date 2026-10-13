## 1. 实验任务

- [x] 1.1 实现 `run_experiment_task`，用 `entity_id` 执行已有实验并把状态与错误写回任务记录和实验记录；用单元测试验证成功、失败和不存在的实验
- [x] 1.2 把实验任务注册到 Celery `default` 队列，并用测试确认任务名可被 worker 发现

## 2. 导入任务

- [x] 2.1 实现 `run_import_task`，执行已有导入作业并同步进度与最终状态；用单元测试验证进度、完成，以及作业不存在时拒绝执行
- [x] 2.2 把导入任务注册到 Celery `default` 队列，并用测试确认任务名可被 worker 发现

## 3. 基准任务

- [x] 3.1 实现 `run_benchmark_task`，执行已有基准运行并写回准确率、成本、完成或失败状态；用单元测试验证完成、失败和取消后不再标成完成
- [x] 3.2 把基准任务注册到 Celery `default` 队列，并用测试确认任务名可被 worker 发现

## 4. 补齐验收测试

- [x] 4.1 通过 TaskManager 提交实验、导入、基准任务，断言立即返回任务标识，任务可查询为 pending，且实验与基准记录仍保持 pending
- [x] 4.2 为实验任务补测试：记录不属于该用户、状态不是 pending，以及 execute_experiment 以 recover=False 构造服务
- [ ] 4.3 为导入任务补测试：作业失败时把 result.detail 写入任务错误信息
- [ ] 4.4 为基准任务补测试：记录不属于该用户、状态不是 pending，以及 execute_benchmark 以 recover=False 构造服务
