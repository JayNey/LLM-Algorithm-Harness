# 验证报告：runs-resume-visibility

- 日期：2026-09-30
- 工作流：Comet Classic tweak（verify_mode: full，含 delta spec）
- 分支：`tweak/20260930/runs-resume-visibility`
- 实现：738df1b
- 审查方式：独立审查者全量审查

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务完成 | PASS | 8/8 `[x]` |
| 2 | 实现符合 design.md | PASS | summarize_run/find_matching_unfinished/runs list/clean/启动提示均按设计 |
| 3 | Design Doc 一致性 | N/A | tweak 预设无 Superpowers Design Doc |
| 4 | 能力规格场景全部通过 | PASS | 3 个 Requirement 全部 Scenario 有对应测试 |
| 5 | proposal.md 目标满足 | PASS | runs list、启动提示、清理、成本口径均已实现；交互式询问按 proposal 声明不做 |
| 6 | delta spec 与 design 无矛盾 | PASS | validate 通过 |
| 7 | 关联设计文档可定位 | N/A | 无 docs/superpowers/specs 关联文档 |

## Delta spec Scenario 覆盖

| Scenario | 测试 |
|----------|------|
| 列出可恢复运行 | `test_list_defaults_to_resumable`、`test_list_all_includes_completed` |
| 成本口径 | `test_unknown_usage_counted_not_accumulated` |
| 提示匹配的未完成运行 | `TestFindMatchingUnfinished`（指纹匹配语义）+ `test_fingerprint_includes_budget_and_dataset` |
| 无匹配不提示 | `TestFindMatchingUnfinished`（不匹配集合为空） |
| 清理范围 | `test_clean_force_removes_only_completed` |
| 确认模式 | `test_clean_without_confirm_skips_on_n` |

## 验证命令

- `comet check run runs-resume-visibility build --local -- python3 -m pytest -q --cov-fail-under=0` → exit=0（734 passed / 4 skipped）
- `comet classic openspec -- validate runs-resume-visibility` → valid
- **覆盖率门禁说明**：同前——上游基线约 82%，90% 门禁不可达，以全量测试通过为准。

## 集成代码审查

- 第一轮（全量 diff，738df1b）：requests-changes——4 IMPORTANT（runs 子命令缺 --output 致非默认目录不可管理；启动提示 Scenario 无真实测试；README 未更新；clean 确认在 EOF stdin 下崩溃）+ 3 WARNING（坏记录拖垮 list、可能建议恢复执行中运行、提示命令缺前提说明）+ 7 SUGGESTION。
- 处置：commit 33da089——全部 IMPORTANT/WARNING 修复（含过程中自查发现并修正的 runs_sub_parser 变量遮蔽缺陷）；提取 maybe_print_resume_hint 并补真实打印路径测试；README 章节落地；EOF 安全；逐单元韧性；hint 文案补并发告诫与前提；指纹惰性计算；--output 真实子进程回归锁。
- 第二轮（定点复审 33da089）：**approves**。九个子命令路由实测正常；EOF/坏记录场景端到端复验。
- 接受的非阻塞残留：unknown-usage 备注行无 CLI 级断言（summarize 层已覆盖）；hint 预筛内联字面量一致性债；clean 对 KeyboardInterrupt 逐条跳过。

## 结论

全部检查通过，无 CRITICAL/IMPORTANT 未决项。**验证通过（verify_result: pass）**，可进入归档前最终确认。
