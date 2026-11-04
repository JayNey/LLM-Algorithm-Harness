# Issue #341 评估执行独占验证

Change: evaluation-execution-ownership。工作分支：comet/evaluation-execution-ownership。
用户选择新分支、继续 tweak；范围为单一 change，六个实现/测试文件。

## 实现与设计一致性

共享任务卷 data/tasks/.execution/<SHA-256(evaluation_id)>.lock 持有 OS 排他锁，覆盖 worker 全部执行、SQL、检查点、结果、费用和产物回调。锁文件保持稳定，不删除或替换；无锁原语的平台拒绝执行。进程死亡释放执行权，存活执行者不会因 TTL 误判被接管。

两个恢复入口都持有同一锁直到事务提交与消息发布完成，避免探测后竞态；拒绝活跃执行者期间恢复。TaskService 的等待选项让取消和异常路径在后台线程收尾后才释放锁。原有调用方默认取消行为保持。

## 验证证据

- 最小重复执行回归先失败：持锁时没有抛 Retry，进入了模型替身；修复后通过。
- 两恢复入口的发布边界测试先失败：发布期间可以重新取得锁；保持锁到发布结束后通过。
- 定向回归：328 passed，包含 worker、TaskService、两恢复入口、业务恢复、工作流契约与跨平台文件锁。
- 两个独立 worker 进程使用实际 SQLite 和 TaskService，仅一个进入模型替身，另一份重投递；后续终态重复投递不新增调用或成本。
- 真实终止持锁进程后，新进程恢复 running 检查点；最终一条结果、completed_count=1、spent_usd=0.01。未确认的外部调用可能重试，测试不伪称其费用已被确认。
- 取消在途调用时，其他执行者仍不能取得锁；线程结束后可以取得锁。暂停立即恢复两个入口均拒绝，退出后两入口均能恢复。
- #337 的五个提交窗口 × 两种单元数、running 检查点恢复与指纹校验继续通过；成本差额记账与确认结果重放保持。
- ruff check .、black --check .、显式编码扫描、compileall src api 和 OpenSpec strict validate 通过。
- mypy src/ --ignore-missing-imports：当前与原始基线均为相同四个既有错误（api/files/parsing.py:93、api/progress.py:139、api/services/cost_alert_service.py:170-171），本 change 无新增类型错误。
- 完整 pytest：3811 passed、18 skipped，覆盖率 92.94%，耗时 556.05 秒。沙箱禁止本地监听，已在允许 127.0.0.1 临时端口的环境复跑完整套件通过。

## 独立集成审查

独立 reviewer 复现并指出恢复入口探测后竞态；修复后原复现拒绝并发恢复。最终反馈：无剩余 Critical/Important。原有竞争恢复测试的同步屏障暴露准入顺序变化；将额度检查放回非阻塞执行锁之前，取得失败立即回滚数据库准入锁，原测试与独立竞态复现均通过，审查确认无锁顺序死锁。取消与异常线程收尾、同代重试、锁失败关闭及检查点重放边界均已检查。Tweak 无独立 Superpowers Design Doc/Plan，按 change design.md 对照，完整 delta 四场景均有回归覆盖。

## 适用边界

所有 API/worker 必须共享同一支持 OS 文件锁的任务卷（现有 compose 的 task_data）。不支持各 worker 使用独立任务目录。活着但挂起的执行者须先被运维终止，才允许故障接管。供应商已执行但尚未确认到检查点的崩溃窗口仍保留 uncertain 重试语义，不宣称外部付费调用恰好一次。未调用真实模型或生产服务；未验证真实 Redis/Celery broker 双 worker 集群或 PostgreSQL 环境。

## 结论

PASS：2/2 tasks、1 项增量需求、4 个场景完整覆盖，设计与实现一致，无剩余 Critical/Important。类型检查的四项基线问题与本变更无关，已明确记录。等待归档前最终确认。
