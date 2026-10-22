## 问题与根因

评估任务开启了 `acks_late` 与 `reject_on_worker_lost`，但 worker 只把 paused/failed 检查点识别为恢复任务。worker 丢失后遗留 running 检查点，重投递会调用 create，因相同 run_id 已存在而失败。TaskService 的 resume 已能重新排队 running 单元，问题在 worker 的恢复判定。

## 修复目标

running 检查点走恢复路径，保留已完成单元、结果、费用及单元身份，只执行未完成工作；继续校验配置与数据指纹。

## 失败证据

`python3 -m pytest tests/test_celery_tasks.py -k redelivery -q --no-cov`：3 failed。真实执行首单元后第二单元抛 SystemExit，磁盘检查点包含 completed/running/queued。重投递在 TaskService.create 抛 `ValueError: Task 'eval-…' already exists`；两个指纹测试也被同一异常提前阻断，未进入应有的指纹校验。根因为 worker 的状态白名单遗漏 running，与测试环境无关。

## 能力与影响

修改既有 `api/evaluation-execution` 的恢复要求与验收场景，不新增 capability、接口、schema 或依赖。实现范围为 src/tasks/evaluation.py，回归测试位于 tests/test_celery_tasks.py。
