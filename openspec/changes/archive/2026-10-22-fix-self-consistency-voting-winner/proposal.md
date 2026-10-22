## 问题描述

Self-Consistency 已通过投票选择最常见的通过测试的候选，但返回的 `generated_code` 来自最后一个候选。当最后一个候选落选、测试失败或未提取到代码时，返回的代码与成功状态、测试结果不一致。

## 根因分析

`_vote_on_candidates()` 仅返回胜者的 sandbox result，没有传递选中代码。`execute()` 调用 `StrategyBase.create_execution_result()`，该通用方法按顺序策略约定从最后一次迭代提取代码，因此丢失投票选择信息。

## 修复目标

- 成功时返回投票胜者代码，确保与最终沙箱结果一致。
- 保留原始候选顺序、完整 traces、token 汇总、票数和已有平票行为。
- 全失败时保留最后一个候选的回退行为。

## 范围

仅修改 Self-Consistency 实现及相关测试；不改变公共接口、投票规则或既有 spec 验收场景，无需 delta spec。用户已选择新建分支，工作分支为 `hotfix/20261022/fix-self-consistency-voting-winner`。

## 失败复现证据

运行 `python3 -m pytest tests/strategies/test_self_consistency_e2e_report.py -k generated_code_matches_selected_candidate --no-cov -q`：6 failed、4 passed。输入候选 `print(5)`、`print(5)`、`print(2 + 3)` 时投票频次为 2，但 `generated_code` 实际返回 `print(2 + 3)`，期望为 `print(5)`。末尾测试失败、无代码、模型调用失败、平票及唯一通过位于中间的场景也都在同一代码断言失败，确认问题位于结果装配而非投票计数或测试环境。
