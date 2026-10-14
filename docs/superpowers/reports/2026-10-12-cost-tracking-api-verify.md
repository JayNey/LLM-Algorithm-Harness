# 验证报告：cost-tracking-api（上游 issue #154）

- 日期：2026-10-12
- 分支：comet/cost-tracking-api（基线 fa9ad3f，含 #176/#177）
- 验证模式：full（14 变更文件 / 1 delta capability / 9 任务）；verify_mode=full（含 delta spec）
- 独立审查：第一轮 requests-changes（4 IMPORTANT + 4 WARNING + 5 SUGGESTION），全部修复；定点复审结论见 §审查结论

## 检查结果简表

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 9/9 `[x]` |
| 2 | 实现与 tasks 一致 | PASS | `git diff fa9ad3f..HEAD` = 迁移 0003 + 四 ORM + cost 服务 + 路由 + 14 测试 + 文档，无超范围改动 |
| 3 | 构建/测试通过（Runtime 证据） | PASS | build check exit=0（log 400893f0，修复前基线 1315 passed / cov 90.44%）；修复后 fresh check 见 §验证证据 |
| 4 | 相关测试通过 | PASS | tests/test_api_cost.py 14 条全过（含 6 条审查回归） |
| 5 | 无安全问题 | PASS | owner 过滤全覆盖；webhook/邮件目标响应脱敏（含查询串）；dataset 约束不变；定价覆盖的全局可写性作为信任边界在文档/PR 中显式声明，治理随 #159 |
| 6 | 最终集成代码审查 | PASS | 第一轮 13 项发现全部修复并有回归测试；定点复审见 §审查结论 |
| 7 | 核心场景与边界验证 | PASS | 见 §场景核对 |

## OpenSpec validate

`comet classic openspec -- validate cost-tracking-api` → valid

## 场景核对（delta spec: api/cost-management）

| Requirement / Scenario | 核对方式 | 结果 |
|---|---|---|
| 成本查询 · 跨表任务解析 | test_task_cost_*（evaluations 分支）+ test_benchmark_run_cost_via_task_endpoint（benchmarks 分支，含 model/cost）；未知 id → 404、跨用户 → 404 | PASS |
| 成本查询 · 空时间段返回空序列 | test_period_validation_and_empty_window（summary 0/trends []/breakdown 三 dict 全空）+ 非法/倒置时间段 400 | PASS |
| 预算 · 未配置预算的用量查询 | test_usage_without_budget_has_caps_none（cap/percentage 为 null） | PASS |
| 预算 · upsert 与部分更新 | test_upsert_get_and_usage + test_patch_keeps_action_and_unmentioned_fields（action/difficulty_caps 不被 PATCH 重置） | PASS |
| 预警 · 非法规则被拒绝 | test_invalid_rules_are_rejected（threshold 0 / 未知 channel / 缺 target 均 400） | PASS |
| 预警 · 目标脱敏 | test_rule_crud_with_masked_target（响应含 host/***，secret 不出现） | PASS |
| 定价 · 覆盖生效且可追溯 | test_catalog_override_and_history（两次覆盖，目录取最新、历史两条按时间倒序）；非正价格 400 | PASS |

## 验证证据

- build check（Runtime）：exit=0，log `openspec/changes/cost-tracking-api/.comet/checks/400893f0-fdbe-45e9-ba06-d488a82a9075.log`（1315 passed，coverage 90.44%，门禁 90 原样）
- 修复后 fresh check 与 verify check：见 `.comet/checks/` 最新日志（1318 passed，coverage ≥90）

## 审查结论

**第一轮**（general-purpose 子代理，逐行 14 文件 diff，实测 fromisoformat 行为与 cost_optimizer 契约）：`requests-changes`，13 项发现，处置如下：

- **IMPORTANT 1（已修复）**：PATCH /budgets 恒重置 action（模型默认 "pause" 永非 None）。修复：action 改 Optional、partial 语义改为逐字段跳过 None；回归 test_patch_keeps_action_and_unmentioned_fields。
- **IMPORTANT 2（已修复）**：date-only `until` 截断到 00:00 漏掉整天。修复：纯日期串解析为当天 [00:00, 23:59:59.999999]；带时区输入换算 UTC；回归测试锁定 date-only until 含当天花费。
- **IMPORTANT 3（已修复）**：合成 comparison 的 accuracy 键名与 build_advisory 契约（`pass_rate_over_total`）不匹配，ranking accuracy 恒 null。修复：改用契约键名。
- **IMPORTANT 4（已修复）**：优化报告 accuracy 分母（全部 completed runs）与 cost 分母（仅 cost-known）口径不一致，且空 model 建桶。重写为单遍聚合。
- **WARNING（已修复）**：update_rule 缺"非 log 通道必须有 target"校验（与 create 对称）。
- **WARNING（已修复）**：design.md 声明的 evaluate 能力表述超前——改为"配置面与数据面，运行期接线随 #149"。
- **WARNING（已修复/显式声明）**：定价覆盖为服务器全局数据且任何认证用户可写——API.md 与 PR 显式声明该信任边界，治理随 #159。
- **WARNING（已修复）**：spec 场景测试缺口——补 benchmarks 分支 task_cost 测试与空窗口 trends/breakdown 断言。
- **SUGGESTION（已修复）**：_mask_target 查询串泄露（先取 authority 再截 ?/#）；budgets 迁移双重唯一（保留唯一索引）；POST 全量替换语义写入 API.md；零花费评估不再计入 task_count/趋势；model_id 路径参数限长；并发建预算 IntegrityError → 400；未用的 _pricing_lock 移除。

**第二轮定点复审**：见本节末尾（结论返回后更新）。

## 已知豁免

- 运行期预警触发/投递与 runner 侧定价读取不在本 change（#149/#159，认领评论与设计文档已声明）
- alert/smtp 目标明文入库（响应侧脱敏），加密存储延后至统一 secrets 任务
- 难度用量为比例估计（响应 basis 注明）；evaluation 的 model 记为 "evaluation-run" 占位（评估表无模型列，#149 可加）
- 时间戳 naive UTC：全仓约定

## 交付门禁（2026-10-12）

推送 `comet/cost-tracking-api` 并创建关联 #154 的 PR（base: JayNey/main），检查远端 CI，交付结果记录于 delivery。
