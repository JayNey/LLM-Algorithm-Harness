# experiment-queue-safety 验证报告

日期：2026-10-28。关联 GitHub issue #296，前置 #295 / PR #303 已合并。
分支：`comet/experiment-queue-safety`，基线 `5d586157ad2c5ddb02e8a657da6a8b99c48646f9`。

## 结论

PASS。3/3 任务完成，2 个能力的 delta 与实现及精简 design 一致。没有未解决的正确性、安全或验收问题。
用户选择独立分支并继续 tweak，生产和测试文件均属于已确认的前后端修复范围；不增加 schema 或新的 API 端点。tweak 不要求单独 Superpowers Design Doc/plan。状态默认 `review_mode: off`，因此未派发自动代码审查；仍对照最终 diff 完成验收、所有者隔离与事务边界检查。

## 验收映射

| 场景 | 实现与证据 |
| --- | --- |
| 顺序/多进程并发启动最多一个任务 | `ExperimentService.start_experiment` 在读取前取得所属实验数据库写锁，检查已存在任务，直到落库提交才释放。`test_experiment_queue_safety.py` 的顺序与 3 个 spawn 进程测试；修复前实际发布 3 次，修复后仅 1 次。HTTP 回归验证首次 202、重复 400。 |
| 排队删除与启动竞争 | 启动/删除共用实验行锁；查询所有 pending/running/paused 任务而非只看业务 running。测试覆盖各活动状态及删除/启动两种先后顺序。保留终态任务记录供迟到取消消息读取。 |
| 刷新恢复关联、操作正确 | 详情/列表按 owner、task_type、entity_id 返回 task_id；列表批量查关联。前端优先使用明确关联，旧接口查询 pending/running/paused 的全部页。client 测试及 Chrome queued、unqueued、legacy-loading、legacy-error、terminal 场景通过。 |
| 发布失败及模糊成功 | 使用已有 enqueue_task 条件失败更新，同步任务和实验为 failed；并发 running/cancelled 不被覆盖。服务测试通过。前端启动报错后刷新持久化状态，publish-uncertain 浏览器场景通过。 |
| 用户隔离 | 读/启动/删除均验证 owner；查询关联包含 owner 和 task_type；异主及异类型伪关联不泄漏、不阻止合法提交。服务及既有 API 鉴权回归通过。 |
| 保留 P1 取消同步 | 原有 `test_experiment_cancellation.py` 全部通过；API 取消→刷新→删除增加 pending 场景，running/paused 场景继续通过。通用 TaskManager 与 Worker 未改动。 |

## 执行证据

- RED：新增后端测试修复前 8 failed / 3 passed，失败包括重复发布、删除未拒绝、缺少 task_id；前端 client 新增 3 项复现失败。浏览器复现排队刷新丢失、恢复期间误显启动，以及发布超时后未刷新关联。
- `python3 -m pytest tests/test_experiment_queue_safety.py tests/test_experiment_cancellation.py tests/test_experiment_task.py tests/test_api_experiment_benchmark.py -q --no-cov`：86 passed；之后新增两项 API 参数/场景，`python3 -m pytest tests/test_api_experiment_benchmark.py -q --no-cov`：39 passed。
- `python3 -m pytest -m 'not online'`：3403 passed、11 skipped、14 setup errors，覆盖率 92.70%（超过 90% 门槛）。14 errors 全部来自 `tests/test_deployment_readiness.py` 在受限沙箱绑定 loopback 端口时触发 PermissionError，未进入断言。
- 在允许本地监听端口的环境补跑 `python3 -m pytest tests/test_deployment_readiness.py -q --no-cov`：14 passed，前述环境错误已排除。未通过修改源码规避这些测试。
- `python3 -m mypy --follow-imports=silent api/services/experiment_service.py`：通过。`ruff check`、`black --check`（本次 Python 文件）及 compileall：通过。
- 前端 `npm test`：274 passed；`npm run lint`：0 errors；`npm run build`（含 tsc）：通过。
- `frontend/scripts/verify-experiment-queue.mjs`：本机 Chrome + API fixture，6 场景全通过。fixture 只替换网络响应，执行真实页面；包括刷新、取消请求、操作按钮、旧接口恢复错误/等待及提交超时。没有声明为真实 Broker/浏览器端到端测试。
- `comet classic openspec -- validate experiment-queue-safety --strict`：通过。
- `git diff --check`：通过。

## 已有提示与验证边界

全套件保留依赖外部服务/可选环境的 11 项 skip；未运行真实 Redis/Celery/Docker 集成。并发测试使用真实 SQLite 文件与独立进程；PostgreSQL 采用同一 UPDATE 行锁语义，但本轮没有实际 PostgreSQL 实例测试。前端保留无关 BenchmarkDetailPage 的两条已有 hooks warning，以及已有构建包体积提示；没有新增 lint error。Python 保留已有弃用警告。

## 交付状态

实现已在绑定分支提交，验证通过后等待归档交付方式确认。归档将合并两个主 spec 并移动 change；归档之前不推送、不创建 PR。
