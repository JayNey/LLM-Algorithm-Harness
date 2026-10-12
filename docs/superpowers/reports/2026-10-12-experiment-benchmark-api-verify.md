# 验证报告：experiment-benchmark-api（上游 issue #156）

- 日期：2026-10-12
- 分支：comet/experiment-benchmark-api（基线 fa79b5a，即 #175 合入后的 upstream/main）
- 验证模式：full（19 变更文件 / 1 delta capability / 11 任务）；verify_mode=full（含 delta spec）
- 独立审查：第一轮 requests-changes（1 CRITICAL + 1 IMPORTANT + 3 WARNING + 2 SUGGESTION），全部修复后经定点复审（见 §审查结论）

## 检查结果简表

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 11/11 `[x]` |
| 2 | 实现与 tasks 描述一致 | PASS | `git diff fa79b5a..HEAD` = 迁移 0002 + 四个新 ORM + 三服务三路由 + 分析端点 + 22 条测试 + 文档，无超范围改动 |
| 3 | 构建/测试通过（Runtime 证据） | PASS | build check exit=0（log 9db85abb）：1296+22 passed，coverage ≥90%；verify check 见 §验证证据 |
| 4 | 相关测试通过 | PASS | tests/test_api_experiment_benchmark.py 22 条全过；既有 API 测试（auth/files/database）无回归 |
| 5 | 无安全问题 | PASS | 密钥仅以 api_key_id 出现在请求/持久化中，运行时经 auth.llm_config 服务端解密；dataset_path 受 DATA_ROOT 约束（审查确认无穿越绕过）；owner 过滤覆盖全部读写路径 |
| 6 | 最终集成代码审查 | PASS | 第一轮 requests-changes 的全部发现已修复并有回归测试锁定；定点复审结论见 §审查结论 |
| 7 | 核心场景与边界验证 | PASS | 见 §场景核对 |

## OpenSpec validate

`comet classic openspec -- validate experiment-benchmark-api` → valid

## 场景核对（delta spec: api/experiment-management）

| Requirement / Scenario | 核对方式 | 结果 |
|---|---|---|
| 实验生命周期 · 创建时校验密钥归属 | test_rejects_foreign_api_key（他人 key → 404）；创建时 owned_key + 数据集存在性校验 | PASS |
| 实验生命周期 · 运行与状态迁移 | test_full_lifecycle（pending→running→completed，产物落库）；test_runner_failure_marks_experiment_failed（异常 → failed 附原因）；test_cannot_delete_running_experiment（running 删除 400） | PASS |
| 实验结果分析 · 未完成实验不可取结果 | test_results_rejected_before_completion（pending 时 results/comparison/panel 全 400）；产物文件缺失 → 明确 400 | PASS |
| 帕累托与成本优化 · 非法分析输入 | test_pareto_analyze_rejects_conflicting_experiments（ValueError → 400）；optimize 端点 200 含 ranking | PASS |
| 基准 Suite 与运行管理 · frozen Suite 拒绝变更 | test_suite_crud_and_freeze（freeze 后 PATCH → 400）；test_run_passes_model_and_decrypted_key_to_executor（model+解密密钥真实传入 executor） | PASS |
| 学习曲线追踪 · 空历史返回空曲线 | test_learning_curve_empty_history；两次 run 聚合趋势 test_run_results_and_learning_curve | PASS |
| A/B 测试管理 · 跨用户资源隔离 | test_cross_user_access_is_404 / test_suite_cross_user_access_is_404 / test_ab_test_cross_user_access_is_404；重复 variant id 拒绝 | PASS |

## 验证证据

- build check（Runtime，本会话）：exit=0，log `openspec/changes/experiment-benchmark-api/.comet/checks/9db85abb-6f85-4129-8260-93fe00285e69.log`（1296+22 passed / 4 skipped，coverage 90.42%，门禁 90 原样）
- verify check（Runtime，本会话）：见 `.comet/checks/` 最新日志

## 审查结论

**第一轮**（general-purpose 子代理，逐行读取 19 文件 diff，实测 LLMClient 调用链与认证解密路径）：`requests-changes`，7 项发现：

- **CRITICAL（已修复）**：benchmark run 持久化的 config 缺 `model`，真实执行必以空模型名调用 provider。修复：config 落库含 model，执行读取 `config_dict["model"]`；回归测试断言 executor 收到的 llm_config.model 与解密密钥。
- **IMPORTANT（已修复）**：Suite 全局唯一名冲突触发 IntegrityError → 500。修复：捕获 IntegrityError → ValueError → 400，路由包 call()；全局唯一为有意设计（学习曲线按 suite 聚合，重名歧义），已在文档说明。
- **WARNING（已修复）**：迁移 0002 的表级 UniqueConstraint 与 ORM metadata 不一致（autogenerate 漂移）。已删除表级约束，保留唯一索引。
- **WARNING（已修复）**：spec 场景测试缺口（异常→failed、running 不可删、未完成取结果、Suite/AB 跨用户）。新增 6 条回归测试覆盖。
- **WARNING（已修复）**：实验产物文件缺失时 FileNotFoundError → 500。results/comparison 增加存在性检查与 FileNotFoundError 捕获 → 明确 400，与 ABTest 行为一致。
- **SUGGESTION（已修复）**："dataset file not found" 被 call() 映射 404。消息改为 "dataset file is missing"（映射 400，与输入错误语义一致）。
- **SUGGESTION（已修复）**：delete-running 错误消息指向不存在的 cancel 端点。改为 "wait for it to finish"。

**第二轮定点复审**（同一审查者，只审修复 diff c3cad67）：`approve`。逐项确认：CRITICAL 的 model 接线与解密路径被回归测试锁住；IMPORTANT 的 IntegrityError 捕获经 flush 触发、并发双插同样命中、事务回滚干净；迁移与 ORM metadata 一致；测试缺口全部补齐且无跨测试污染；产物缺失/消息措辞修复到位。**未发现新引入问题**。残余提示（不阻塞）：start 路径 check-then-act 窄窗口与 #151 模式一致（既定约定）；IntegrityError 捕获理论上会吞掉 UUID 主键碰撞（概率可忽略）。

## 已知豁免

- `/pareto/analyze` 与 `/optimize` 用 POST 而非 issue 草案的 GET：无状态分析需随请求携带 payload，GET 不可行；issue 的 `/pareto/frontier` 并入 analyze 响应、`/optimize/ranking` 并入 advisory 响应（ranking 字段），已在 API.md 说明
- ExperimentRunner/ABTestRunner/BenchmarkExecutor 的 src 内部实现不在本 change 范围（有各自测试），API 层经工厂注入隔离
- Suite 名称全局唯一（跨用户）：学习曲线按 suite 聚合的全局标识设计
- api/models.py、api/routes/evaluations.py 的 mypy 报错为上游既有债务（CI mypy 只查 src/）
- 时间戳 naive UTC：全仓约定

## 交付门禁（2026-10-12）

推送 `comet/experiment-benchmark-api` 并创建关联 #156 的 PR（base: JayNey/main），检查远端 CI，交付结果记录于 delivery。
