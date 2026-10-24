# 用户日/月 API 调用计量验证

结论：PASS。change `user-api-call-metering`，分支 `comet/user-api-call-metering`，完整规格核对，三个任务全部完成。Tweak 不要求独立 Superpowers Design Doc/Plan，已对照 change design.md，无规格漂移。

## 完整性与正确性
- 可信用户归属：AuthService.llm_config 绑定 LLMConfig 私有回调，不参与配置输入输出，查询继续遵循现有个人/管理员权限边界。
- 真实尝试：支持提供方成功/失败各一次，重试分别计数；缓存、模型列表和连接验证排除。已有凭证解析路径覆盖 worker 评估、实验、A/B、benchmark。
- 持久化：认证库日/月唯一键原子 UPSERT，同一事务，失败回滚两桶；多连接并发与独立子进程写入、重开存储后保持计数。
- 周期：UTC 自然日/月，完成时间左闭右开；年首、月长及闰年边界通过测试。旧桶保留，无后台清零，不受监控样本裁剪影响。
- 查询：现有 quotas 返回当前用户整数 used、UTC、起止时间、metered 与 null limit，空用量为零。文档明确 best-effort、启用后统计且不回填历史。
- 隐私与隔离：聚合表只含用户 ID、周期、起点与次数；计量异常不替换提供方结果，计量耗时不占用模型重试预算。

## 验证命令与证据
- 初次 RED：新存储测试因缺少 record_user_api_call/user_api_calls 失败；quotas 测试因旧 not_configured 占位失败，随后 GREEN。
- `pytest tests/test_user_call_metering.py tests/test_llm_call_metrics.py tests/test_api_monitoring_service.py tests/test_api_monitoring.py tests/test_api_auth.py tests/test_api_evaluation_options.py tests/test_llm_client_cache.py -q --no-cov`：221 passed。
- 审查修复后 `pytest tests/test_user_call_metering.py tests/test_llm_call_metrics.py tests/test_llm_client.py tests/test_llm_client_cache.py -q --no-cov`：92 passed。
- `pytest tests/test_api_documentation.py -q --no-cov`：22 passed。
- 改动 Python 文件 `ruff check`、`black --check` 通过，`git diff --check` 通过。
- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/user-api-call-metering-wheel`：通过，输出 wheel。
- `comet classic openspec -- validate user-api-call-metering --strict`：通过。
- 定向回归使用 --no-cov；未宣称全仓库覆盖率达标。现有 Pydantic/SQLAlchemy 弃用警告不属于本变更。

## 集成审查
独立 reviewer 发现计量锁等待可能消耗重试预算（P2）。已先以确定性失败测试复现，再从重试预算扣除累计 SDK 结束后计量耗时；修复后 92 项回归通过，原 reviewer 确认修正有效，无其他可行动问题。

## 工作区归因与交付
所有 dirty 路径均属于本 change，无用户已有改动。新增存储结构和完整计量链路沿用用户明确选择的 tweak。归档前仍需用户确认交付方式；尚未同步主 spec、归档、推送或创建 PR。
