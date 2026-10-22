## 修复方案

在 run_evaluation_task 的检查点状态判定中加入 running，复用 TaskService.run(resume=True) 的指纹校验与 _prepare_resume。已确认 completed/failed 单元保留，中断的 running 单元变为 queued 后重跑。

不修改 TaskService、Celery 配置、API 恢复入口或取消语义。此修复针对 worker 丢失后的顺序重投递，不引入多 worker 并发占有协议。

## 验证方案

通过真实 TaskService 与数据库执行三单元评估，在第二单元用 SystemExit 模拟 worker 丢失，确认磁盘检查点为 running，包含 completed/running/queued 单元；再次调用 worker，确认剩余工作完成、首单元不重复、费用与结果正确、单元身份与事件历史保留。另验证 running 检查点的配置及数据指纹不匹配时仍拒绝恢复。

运行新增测试获取 RED，再修复并运行 Celery、TaskService、TaskManager 和 HTTP 集成回归；运行格式、静态检查及构建。
