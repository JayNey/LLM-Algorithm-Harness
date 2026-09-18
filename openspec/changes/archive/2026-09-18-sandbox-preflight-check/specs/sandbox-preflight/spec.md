## Purpose

定义评测执行前的沙箱可用性预检行为，以及沙箱故障在失败分类中的归类。

## ADDED Requirements

### Requirement: 沙箱预检先于模型调用
系统 MUST 在每个策略开始执行题目之前完成一次沙箱可用性探测；探测失败时 MUST 立即中止该策略的执行并以包含修复提示的错误退出，且不发起任何模型 API 调用。

#### Scenario: 沙箱不可用时启动评测
- **WHEN** 沙箱后端不可用且用户启动评测
- **THEN** 运行立即失败并提示修复方法，未发生任何模型调用

#### Scenario: 沙箱可用时正常执行
- **WHEN** 沙箱后端可用
- **THEN** 预检通过，评测按既有流程执行

### Requirement: 用例级沙箱故障归类
用例级 `sandbox_error` MUST 与迭代级沙箱异常同等归类为 `system_error`，不得判为 `wrong_answer`。

#### Scenario: 沙箱返回逐用例故障
- **WHEN** 沙箱执行返回的结果中存在 `sandbox_error` 用例
- **THEN** 该题失败分类为 `system_error`
