# 实验与 A/B 统一费用验证

结论：PASS。Issue #307；change `unified-experiment-ab-costs`；分支
`comet/unified-experiment-ab-costs`；基线 `26139dd06fef9bd52441698d2056b0b9d0d42558`。
采用用户确认的 tweak + 新分支方式，完整验证；4/4 任务完成，3/3 修改需求及其 13 个场景均有实现和测试证据。

## 最终验证证据

- `MPLCONFIGDIR=/tmp/issue307-matplotlib XDG_CACHE_HOME=/tmp/issue307-cache pytest -m 'not online'`：
  **3555 passed、11 skipped、128 warnings**，退出码 0；覆盖率 **92.77%**，达到 90% 门槛。
  此为所有实现和兼容修复完成后的完整运行，耗时 457.58 秒。
- 配额、重试、缓存、费用的最终相关回归：
  `pytest tests/test_user_call_limits.py tests/test_user_call_metering.py tests/test_llm_client.py tests/test_llm_client_cache.py tests/test_spend_execution.py tests/test_spend_records.py -q --no-cov`：
  **116 passed**。新增费用存储及执行测试合计 **27 passed**。
- 真实 HTTP + worker 测试覆盖实验和 A/B 各一条完整路径：创建、入队、真实 runner 调用、暂停时查询费用、恢复、完成、重复投递；真实 SQLite 和回环 HTTP，只有外部 SDK 与 broker 采用替身。
- Verify 阶段重新运行 `pytest tests/test_api_cost.py tests/test_spend_execution.py tests/test_spend_records.py tests/test_celery_tasks.py -q --no-cov`：**114 passed**，退出码 0。
- `ruff check .`、`black --check .`（360 个文件）、
  `python3 scripts/find_missing_encoding.py`（0 项隐式文本编码）、
  `python3 -m compileall -q api src`、`git diff --check` 均通过。
- `UV_CACHE_DIR=/tmp/issue307-uv uv build --offline --out-dir /tmp/issue307-dist --python /opt/homebrew/opt/python@3.11/bin/python3.11`：
  源码包及 wheel 构建成功；已核对 wheel 含新费用服务及迁移 `e0005_spend_records.py`。
- `comet classic openspec -- validate unified-experiment-ab-costs --strict`：通过。

## 需求及场景对应

- **成本查询聚合**：`CostService` 的同一个记录集合供单任务、汇总、趋势、分项、任务费用报告和预算读取。
  `tests/test_api_cost.py` 覆盖跨表解析、空日期窗口、四来源旧契约、同任务多调用去重、UTC 日期边界、其他 owner 隔离、部分已知及完全未知。
- **状态与重复执行**：`tests/test_spend_execution.py` 通过真实模型客户端和 runner 验证中途暂停、取消、失败仍保留已提交费用；恢复检查点不再计入完成单元；HTTP worker 场景验证重复消息不增加金额。
  `tests/test_spend_records.py` 覆盖串行回放及 8 次并发回放只保存一次事件。
- **未知与历史数据**：缺用量、缺价格、无响应分别保存未知，缓存命中记零增量。
  新迁移保留旧业务记录并将历史费用标为不完整；SQLite 非空数据库升级、降级、再次升级通过，既有 PostgreSQL 离线 SQL 可移植性检查通过。
  回填仅导入明确历史价格小计，dry-run 不写费用，重复执行不双计；缺失及畸形材料会报告跳过，旧 A/B 总 tokens 不被重定价估算。
- **预算展示及执行**：全局累计和费用汇总采用相同四来源；新增可归属难度按实际已知调用加入。
  `tests/test_celery_tasks.py` 及费用 HTTP 测试覆盖触顶暂停、分难度、降级、单任务优先、恢复重新检查、其他 owner 和未配置预算兼容。
  原有 evaluation 展示比例估计继续明确注明 basis，执行不使用该估计。

## 独立集成审查闭环

使用 `requesting-code-review` 派发一次独立只读集成 reviewer，并由同一 reviewer 复查修复及最终兼容改动。
最终无未解决 CRITICAL/IMPORTANT 或需要接受的新增偏差：

- 超时后重试成功曾掩盖失败尝试的不确定消耗：每次继续重试前独立保存未知事件，最终成功保存已知金额；记账错误通过专用错误退出，不重试供应商。
- 嵌套畸形历史 JSON 曾中断回填：逐层校验结构，跳过不可验证材料；新增失败测试均转绿。
- 完整回归暴露旧预算精确快照和绕过构造函数的缓存夹具；测试补齐新增字段并只替换缓存依赖。
  最终重试单元测试还验证无观察者的底层客户端，已为可选回调提供不可变默认值；同一 reviewer 确认实例回调互不泄漏。

## 设计一致性与实际限制

实现与 proposal、design.md 及 delta spec 一致，无新增 HTTP 路由、无新前端行为。tweak 预设不要求 Superpowers 深度 Design Doc 或完整 plan。
scale 在 verify 阶段选择 full；虽 CLI 显示嵌套 delta 数为 0，实际 `specs/api/cost-management/spec.md` 存在、OpenSpec 正确识别并通过 strict 验证，本报告按其 3 个需求完整核对。

费用记录仅保存用量、价格、归属及时间，不保存提示词、输出或凭据。供应商已消费但响应永久丢失或数据库提交前进程退出，仍无法提供供应商账单级精确对账；已观察到的无响应尝试保留未知。
历史整体缺口不会因回填部分快照被标为完整。PostgreSQL 实例未做在线验证，已验证离线迁移 SQL；未向真实模型供应商发出付费调用。

`mypy src/ --ignore-missing-imports` 仍退出 1，有 4 项既有错误：
`api/files/parsing.py:93` 的 SafeLoader Any、`api/progress.py:139` 的多余 ignore、
`api/services/cost_alert_service.py:154` 的 metrics 注解及 `:155` 的生成器类型。
通过基线文件的 mypy shadow-file 复测确认基线原有 5 项错误，本次修正了费用服务的一项局部注解，没有引入新错误；不将该命令表述为通过。

Comet 可选上下文插件因全局目录锁权限无法加载，不阻断工作流；没有依赖未加载的上下文或虚构验证证据。

当前实现已提交。Verify 只产生本报告及阶段元数据。用户已在最终归档确认选择 C：合并主 spec、归档并提交，然后推送当前绑定分支并创建 PR；不执行合并或删除分支。

归档已同步 3 项需求至主 spec；补齐该 spec 原有的 Purpose 占位说明后，`comet classic openspec -- validate api/cost-management --type spec --strict` 通过，最终 archive guard 6/6 通过。
