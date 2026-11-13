# 实验与 A/B 模型端点验证

## 完整性与规格覆盖

- 已完成 OpenSpec 任务 1/1。变更为现有 `api/experiment-management` 能力补充一条端点约束，严格规格校验通过。
- 创建入口通过 `ModelSpec` 拒绝非 `null` 的 `base_url`。实验与 A/B 接口回归验证了回环地址、外部 HTTPS 地址及空字符串返回 400，字段错误可定位，业务记录未写入。
- 两条实际 Celery 任务入口的回归验证了旧配置中的地址覆盖会在 Runner 初始化之前被拦截。实验和 A/B 业务记录及任务记录均变为 failed，错误中没有原始地址。
- 正常生命周期测试验证了显式 `null`、模型提供商和温度配置。其他创建和执行测试继续覆盖缺省字段的请求。

## 设计一致性

Worker 继续通过已有凭证解析构造模型配置。两个执行路径均已移除用户地址覆盖，并复用入口的拒绝规则。实验会在解析任何模型凭证前检查所有模型；A/B 保留认证初始化错误的原有处理顺序，随后在读取数据和解析密钥前检查历史配置。风险处理遵循服务端控制请求目的地的做法。[OWASP SSRF 防护指南](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

本次使用 tweak 精简设计，核对 change 内的 design.md。预设审查模式为 off，已对提交差异、入口边界和失败状态回写进行人工式代码核对。

## 验证命令

- 安全回归先失败 8 项，修复后通过 8 项。
- Black、Ruff、Git 差异检查及 Python wheel 构建通过。
- `comet classic openspec -- validate restrict-worker-model-endpoints --strict` 通过。
- `python3 -m pytest -o addopts='' --tb=short -q tests/test_api_experiment_benchmark.py tests/test_experiment_task.py tests/test_ab_test_task.py tests/test_api_versioning.py tests/test_api_auth.py tests/test_llm_client.py` 通过 268 项。
- 结果 PASS。本地验证使用模拟模型客户端和实际任务入口。
