# #157 队列健康与 worker 负载验证报告

日期：2026-10-19（Asia/Shanghai）。初始基线 main：b6437098a55eddb40fd13a62e1328a8abbba16c5；最终追加基线：a563631a322d3d96b24f77bcb85a8901237a0cbb。分支 tweak/20261019/monitoring-queue-health。沿用用户指定的增量 Tweak，PR #204 使用 Refs #157。

## 行为

- 管理员可显式启用 Redis PING 和 Celery worker 负载观测。默认关闭；公开存活检查及 401/403 路径不访问 broker。
- 使用当前 Celery app 的 broker URL，通过 stdin 交给独立探测进程。URL 不出现在命令行和响应中，第三方 stderr 丢弃，stdout 仅安全 JSON。父进程施加每类 0.5–10 秒预算，超时 kill/reap；关闭服务取消进行中探测。
- worker 新增只读 monitoring_snapshot inspect 命令，只读取 active/reserved 请求集合和池报告的 num_processes，不调用 Request.info() 或完整 stats。reserved 排除 active；节点名只作为稳定摘要 ID 返回。升级后需要重启 worker 加载命令。
- 每类每 API 进程最多一个在途探测，成功和失败都按 TTL 缓存并显示年龄；并发刷新返回 unknown/refresh_in_progress，过期结果不冒充新观测。system/status 复用 health 中同一次 worker 观测，TTL=0 也不重复广播。
- 无回复、超时、旧 worker、非法/重复/过量回复分别给出明确状态，未知计数为 null。最多接收 128 个节点，截断和部分观测不生成聚合数。只描述截止时间内收到的回复，cluster_complete=false；reserved 不是 broker 队列长度。
- #149 已完成且主线已有真实 AlgorithmHarness 执行，修正历史 mock、模拟器和待接入 #149 标记。real_evaluation_available=null/execution_readiness=not_checked，表示健康检查没有验证某个模型、凭据或沙箱的运行就绪。

## 测试与审查

- 监控相关首轮回归：174 passed；新增单元/HTTP 回归：40 passed，涵盖真实子进程超时与回收、并发取消、缓存年龄/过期、回复安全、认证和聚合复用。
- 隔离真实链路：1 passed。临时 Redis 7 容器仅绑定随机本机端口；独立 solo Celery worker 只监听隔离测试队列。实际 Redis PING 与 monitoring_snapshot 返回 ok，worker_count=1、active=0、reserved=0、concurrency=1。没有提交业务任务或调用 LLM。
- 初始基线全量离线：1789 passed、7 skipped，原口径覆盖率 94.02%，200.93 秒。原始日志：/private/tmp/monitoring-queue-health-full.log。该口径包含测试文件，不能直接与后续 #201 的 src/API 口径比较。真实链路需显式 MONITOR_QUEUE_TEST_BROKER；常规回归不要求外部 Redis。
- Bugbot 独立审查完整分支差异：无新增发现。审查者单独运行新增测试 40 passed，未修改文件。
- Ruff、Black（310 文件）、显式编码扫描（0 处）、mypy src（97 文件）、监控/路由（12 文件）、OpenSpec strict：通过。SQLAlchemy 新版本需为已有 counts 局部变量补充 dict[str,int] 注解，未改变查询行为。

## 规格一致性

- “禁用或未经授权”：disabled/closed 零启动测试，HTTP 公开存活和 401/403 边界测试。
- “成功及缺失观测”：真实 Redis/worker 测试，旧版本、重复、无回复、非法计数和上限回归。
- “卡住、并发和关闭”：真实 sleep 子进程超时 kill/reap、并发不重复启动、关闭取消以及缓存过期测试。
- “非可信回复和错误”：主机摘要、敏感字段丢弃、子协议再次校验、非法 stdout/异常/超大输出、URL 超时参数覆盖回归。
- “worker 在线”：运行能力与 LLM 就绪分开，HTTP 验证能力字段及 responding_celery_workers/cluster_complete=false。

proposal、design、delta spec 与代码一致。Tweak 未创建完整 Classic 技术设计；所有代码与文档均属于本次队列观测范围。实际 Runtime 编译/定向验证和阶段守卫将在交付前记录，不手工设置 pass。

## 限制与剩余范围

- Redis/rediss broker 受支持；未单独探测 result backend。广播有回复窗口，不能据此枚举所有节点或断言无回复的 busy solo worker 已离线。
- 每类探测具有独立预算；system/health 队列部分最坏约两倍预算，另含进程终止清理和其他既有数据库/Docker 检查。
- concurrency 是池报告的执行单元数，未推导 CPU 利用率。LLM 延迟/成功率、跨 worker 缓存、broker 等待队列长度、容器资源和日/月配额仍待后续，#157 不关闭。
- 真实链路为本机隔离 Redis/solo worker；生产集群、TLS 和多 worker 场景依靠部署验证及安全边界单测，未冒充本机生产实测。未发起在线提供商请求。
- 本轮新增提交排除 .comet/.claude/.codex/.agents/skills-lock.json，保持应用 CI 规则。归档和合并按既定确认流程处理。

## 最新主线追加验证

发布前主线新增 #200 角色权限、#201 API 覆盖率门禁、#202 统一错误响应。已无冲突重放本轮提交，保留所有新规则。current_role 仍从服务端管理员 UUID 白名单派生，与监控授权一致；错误和 CORS 中间件仍在请求统计覆盖范围内。

- 相关认证/监控/错误回归：177 passed。增强已有 status 集成用例，实际创建 pending 任务，在启用队列观测前后比较完整任务快照，验证不修改业务状态。
- 最终完整离线：1821 passed、7 skipped，src/API 合计覆盖率 91.25%，217.47 秒。命令：python -m pytest -m 'not online' -o faulthandler_timeout=60。原始日志：/private/tmp/monitoring-queue-health-final-full.log。
- 独立分项门禁：coverage report --include=src/* --fail-under=90，实际 90.45%；--include=api/* --fail-under=81，实际 92.85%，均退出 0。没有降低主线门禁。
- Bugbot 对新增主线影响补查无新增发现，独立 HTTP 回归 83 passed。Ruff、Black（311 文件）通过。
- PR #204 已创建为草稿，最终 Runtime 记录和当前头平台 CI 完成后转为可审查状态。

Comet 0.4.1 在 build 阶段提前设置 verify 配置时曾返回 tweak build configuration is incomplete；state check 和 doctor 对本 change 均报告有效。完成全部六项任务后，经公开 build 守卫推进到 verify，再设置 full 与报告路径成功。没有直接修改 Runtime 自有状态。

最终实际 Runtime 编译检查成功，日志 c21457c1-e522-4d81-b4de-36164457f9d0.log；定向验证 92 项通过，日志 1e6fdb7c-e1bb-46a3-823e-900acad46acd.log。build 守卫 14/14、verify 守卫 5/5 通过，由守卫记录 verify_result=pass、phase=archive。保留 branch_status=pending 和 archive_confirmation=pending，未自动归档或合并。真实链路测试的隔离 worker 和 Redis 容器已清理。

## #203 合并后的最终回归

主线新合并 #203 的 803 项 API 端点单测。GitHub 合并树 CI 暴露 `/system/status` 的旧夹具将 health 模拟为 `{}`，与真实 `health.checks.workers` 契约不符。已在最新 main 重现 500/KeyError，再仅修正单测夹具并增加断言，验证 status 复用 health 的 worker 观测、health 只调用一次且不直接再次探测；未修改生产探测逻辑。

- 新主线端点与队列监控回归：843 passed。原始日志：/private/tmp/monitoring-queue-health-unit-compatibility.log。
- 最终完整离线：2624 passed、7 skipped，217.94 秒；src/API 合计覆盖率 91.50%。原始日志：/private/tmp/monitoring-queue-health-current-main-full.log。
- 分项覆盖率门禁保持不变：src 90.46%（门禁 90%），API 93.57%（门禁 81%），退出均为 0。
- Bugbot 补审无新增发现，独立运行 6 项 system/status 单测通过。Ruff、Black（312 文件）、编码检查和 OpenSpec strict 均通过。
- PR #204 已转为可审查状态，重放到上述最新主线后将发布新头重新运行平台 CI。此前头 bd68e707 的失败不作为新头结果。

最新主线的 Runtime 实测编译通过（993b27ed-4ba4-431f-8d2b-a8a860b2f858.log），定向验证通过（735b1ff3-8ef7-442a-a920-51c07a1981d4.log）。build 守卫 14/14、verify 守卫 5/5 通过，状态为 archive/verify_result=pass，归档确认仍 pending。
