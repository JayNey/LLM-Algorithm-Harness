# Proposal: 修复代码审查发现的三个缺陷

## 问题描述

代码审查发现了三个需要修复的缺陷：

1. **src/harness.py:163** - 隐藏评估失败时无条件覆盖错误信息
   - 当策略在公开测试中失败并产生特定错误信息，且隐藏评估也失败时，代码无条件地用通用的"Hidden evaluation failed"覆盖了`result.error_message`
   - 这导致丢失了公开测试失败的具体诊断信息，影响调试效率

2. **src/strategies/multi_round_feedback.py:134** - 冗余的赋值语句
   - 在`if success:`块内执行`success = True`语句
   - 此时success已经为True（来自第130行），该赋值无效且属于死代码

3. **src/strategies/multi_round_feedback.py:168** - 合并沙箱结果时丢失系统错误状态
   - `_merge_sandbox_results`方法在合并公开和反馈结果时，resource_statuses集合只包含`timeout`、`memory_error`、`output_limit`、`process_limit`
   - 缺少`sandbox_error`和`backend_unavailable`，导致这些系统错误被错误分类为普通失败（`status='failed'`）而非保留系统错误状态

## 根因分析

1. **错误信息覆盖问题（harness.py:163）**
   - 根因：未考虑保留原始错误信息的情况，直接赋值覆盖
   - 原有逻辑假设隐藏评估失败时可以丢弃公开测试的错误详情，但实际上公开测试的错误信息对调试更有价值

2. **冗余赋值问题（multi_round_feedback.py:134）**
   - 根因：代码逻辑重复，可能是重构后遗留的死代码
   - 第130行已经从`sandbox_result.all_passed`赋值给success，第134行的重复赋值无实际作用

3. **系统错误状态丢失问题（multi_round_feedback.py:168）**
   - 根因：resource_statuses集合不完整，未涵盖所有系统级错误类型
   - 导致沙箱错误和后端不可用被误分类为wrong_answer而非system_error

## 修复目标

1. 保留原始错误信息：当隐藏评估失败时，保留公开测试的具体error_message，而不是用通用信息覆盖
2. 移除冗余代码：删除multi_round_feedback.py:134行的无效赋值语句
3. 完善系统错误识别：在resource_statuses集合中添加`sandbox_error`和`backend_unavailable`，确保系统错误被正确分类
