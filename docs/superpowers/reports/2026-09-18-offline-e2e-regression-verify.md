# 验证报告：offline-e2e-regression

- 日期：2026-09-18
- 变更范围：`2431fa3` → HEAD（分支 `tweak/20260918/offline-e2e-regression`）
- 验证模式：full（delta spec `offline-regression`，4 项 Requirement / 7 个 Scenario）
- 关联：上游 issue JayNey/LLM-Algorithm-Harness#20

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部完成 | PASS | 6/6 勾选 |
| 2 | 实现符合 design.md 决策 | PASS | 替身注入沿用 src.harness.LLMClient 缝隙、空策略收紧为显式报错、断言以落盘文件为准、online 跳过用子进程断言 |
| 3 | Design Doc | N/A | tweak 预设无独立 Design Doc |
| 4 | 能力规格场景通过 | PASS | 映射见下 |
| 5 | proposal 目标满足 | PASS | 成功/失败链路 + 三类负向输入 + 文档区分全部落地 |
| 6 | delta spec 与 design 无矛盾 | PASS | 一致（缺失数据集场景按审查意见补齐 `--dataset` 形式测试与错误信息断言） |
| 7 | 关联文档可定位 | N/A | 同 3 |

## 规格场景 → 证据映射

- 离线端到端成功链路 → `test_e2e_success_chain_records_exact_results`（in-process main() 全链路：argparse→load_config→真实 ProblemLoader→host 沙箱真实预检与执行→真实 save_results 落盘；断言 summary solved=1、failure_category 空、token=15、llm_traces）
- 离线端到端失败链路 → `test_e2e_failure_chain_records_wrong_answer_precisely`（wrong_answer + actual=101/expected=2 逐用例断言）
- 负向输入显式失败
  - 缺失数据集 → `test_missing_dataset_fails_without_output_dir`（config 路径）与 `test_missing_dataset_flag_reports_error`（`--dataset` 路径，断言 stderr 含缺失文件名）
  - 坏配置文件 → `test_bad_config_fails_without_output_dir`
  - 空策略列表 → `test_run_without_strategies_raises`（harness 层 ValueError）+ `test_empty_strategies_fails_via_cli`（CLI exit 1，实际由 apply_cli_overrides 既有校验拦截）
- 验证记录区分 → `test_online_verification_skips_without_credentials`（无凭证子进程运行断言摘要行 1 skipped 且无 passed）+ README 测试章节的替身/真实验证区分表

## 独立集成代码审查

- 结论 pass。审查实测确认：端到端为 in-process main() 全链路、patch 点是运行路径唯一构造点（save_results/metadata/latest.json 真实落盘）、断言稳定（token=15 可精确推导、无时间戳断言）、空策略收紧无既有调用方受影响、online 跳过测试在设键环境下亦不失败。
- 发现与处置（1 WARNING + 4 SUGGESTION，已全部处置）：
  1. WARNING「`--help` 子进程缺 cwd，非仓库根运行时脆弱」→ 已补 cwd=仓库根
  2. SUGGESTION「online 跳过断言为恒真式」→ 改为对 pytest 摘要行的精确断言（1 skipped 且无 passed）
  3. SUGGESTION「子命令断言为子串匹配过弱」→ 强化断言（usage + `--dataset` 参数可见）
  4. SUGGESTION「新增 harness.run() 守卫在 CLI 路径被 apply_cli_overrides 前置拦截」→ 行为符合 spec；harness 层由直连单元测试覆盖，记录为已知分层
  5. SUGGESTION「缺失数据集场景与 spec 措辞（`--dataset`、错误信息）不完全对应」→ 已补 `--dataset` 形式测试并断言 stderr 含缺失文件名

## 运行时检查

- Build：`comet check run build --local` exit=0（fd3175f8 日志）；Verify：exit=0，400 passed + 4 skipped，覆盖率 90.02%（b581909a 日志）
- OpenSpec 严格校验：valid

## 结论

检查项全部通过，审查发现项全部闭环。验证通过。
