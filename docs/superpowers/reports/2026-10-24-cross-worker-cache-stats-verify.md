# cross-worker-cache-stats 验证报告

结论：PASS。3/3 任务完成，1 个修改需求的 6 个场景均有实现及测试覆盖。无新增生产代码；已有聚合逻辑符合目标，本次补齐验收、明确公式及文档。

## 完整性
proposal、design、tasks、delta spec 均已读取；任务全部勾选。现有缓存监控逻辑位于 api/monitoring/store.py:132–235，实际采集桥接位于 api/monitoring/llm_metrics.py，API 读取位于 api/monitoring/probes.py:249。文档变更仅涉及缓存统计口径及过时待办。

## 正确性与场景覆盖
- 真实命中与未命中：test_worker_cache_real_client_shared_collection；验证真实 LLMClient、容量去重及采集失败隔离。
- 跨进程和共享目录：test_worker_cache_overall_rate_weights_cross_process_counts；两个独立进程各重复上报，得到 hits=9、misses=91、hit_rate=0.09，容量仅计一次。
- 不可用或陈旧：已有 snapshots_idempotent_bounded_and_stale 与 cross_process_disabled_and_read_failure 测试覆盖无观测、陈旧容量、禁用及读取失败。
- 不同 Worker 请求量不均：新增两个独立进程场景验证按请求数加权，拒绝 45% 算术平均结果。
- 重复更新与过期退出：新增 updated_snapshot_and_expiry_change_rate 验证覆盖更新后 19/110，过期退出后 0/90。
- 零请求：新增参数化测试覆盖启用和禁用缓存，均返回 null；全未命中返回 0.0。

## 一致性与审查
实现遵循 design 的共享数据库、实例累计快照及容量去重决策，无漂移。tweak 不要求独立 Superpowers Design Doc/plan；本次核对 change/design.md。沿用 review_mode=off，按预设跳过自动 reviewer；人工检查最终 diff，无正确性、安全或边界问题。没有新增依赖、数据库 schema 或公开 API。业务改动为测试和文档两个文件；流程文件为 Comet 自动产物。

## 执行证据
- pytest tests/test_api_monitoring_probes.py -k worker_cache --no-cov -q：9 passed。
- pytest tests/test_api_monitoring_probes.py tests/test_api_monitoring.py tests/unit/test_api_endpoints.py --no-cov -q：893 passed，19 条已有 Pydantic/SQLAlchemy 弃用警告。
- verify 阶段 pytest tests/test_api_monitoring_probes.py --no-cov -q：27 passed，5 条已有 Pydantic 弃用警告。
- python3 -m compileall -q api/monitoring src/cache.py src/llm_client.py：通过。
- python3 -m ruff check tests/test_api_monitoring_probes.py：通过。
- python3 -m black --check tests/test_api_monitoring_probes.py：通过。
- comet classic openspec -- validate cross-worker-cache-stats --strict：通过。
- git diff --check：通过。

本次未运行全仓库测试或在线提供商验证；相关测试未启用全仓库覆盖率门槛。

## 范围限制
Worker 与 API 需共享 AUTH_DATABASE_PATH。结果是保留实例生命周期计数的整体比率，不是全群集总账，也不是保留窗口内请求数。到期或被数量上限淘汰的快照退出统计。零查询为 null，禁用缓存调用不计入分母。cluster_complete=false。

## 流程说明
Comet 在 build 阶段提前执行 scale/set verify_mode 返回“tweak build configuration is incomplete”；build guard 检查全部 13 项通过，正常推进 verify 后 scale 和 verify_mode 设置均成功。未修改 Runtime 或手工伪造状态。comet task 插件因全局锁文件写入权限失败，按技能约定不阻断变更。

## 归档后检查
用户选择 C：归档、推送当前绑定分支并创建 PR。归档完整性 guard 通过，主规格普通校验通过。对主规格额外运行严格校验时，原有 Purpose 不足 50 字的 WARNING 导致非零退出；与归档前 HEAD 对照确认该 Purpose 未变化。本次 change 的严格校验通过。
