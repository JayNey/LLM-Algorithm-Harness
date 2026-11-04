# 构建证据
- 149 项相关测试通过（评估任务、产物发布、TaskService、HTTP 工作流）。沙箱内有 1 项端口权限错误，放开本机网络权限后 149 项全通过。
- 真实 Redis（独立 16379 端口、无持久化）与 prefork Celery：文件提交后 os._exit(73)，日志确认 WorkerLostError 和同消息自动重投递；p0/p1 各调用一次、SQL 2 行、费用 0.02、complete 快照，1 项通过。
- 文件提交前/后、SQL 提交前/后、最终文件提交后，1/2 单元共 10 个确定性回归；修复前 6 项失败，修复后通过。补充预算检查、失败单元及 HTTP complete 导出恢复。
- compileall、ruff、black、OpenSpec strict validate、git diff --check 通过。
- 独立代码审查 review_issue337 无 actionable findings。Runtime direct 预设保留 review_mode=off，但实际已执行独立审查。
- bare pytest 已执行，约 20% 时因已确认的本机监听权限错误中断，未完成全量覆盖率验收。已出现的 4 个错误用例（test_api_cost.py 两项 TestPricing 及 experiment/ab 两项 real_worker_spend）在放开本机网络权限后全部通过。
- mypy 当前源码与 git HEAD 原始源码均为相同 11 项错误（缺 celery/kombu/yaml/scipy stub、api/files/parsing.py:93、api/progress.py:139、api/services/cost_alert_service.py:170-171）；无新增类型错误。
