# Reflexion Strategy Specification

## Purpose

通过“失败归因 → 代码修复”的循环降低模型重复犯错，同时保留可审计的反思记录。

## ADDED Requirements

### Requirement: 可选择的反思策略

系统 MUST 注册名称为 `reflexion` 的策略，并沿用现有 `StrategyConfig.max_iterations` 控制最多代码修复轮数。

#### Scenario: 通过配置运行反思策略

- **Given** 配置包含 `{ "name": "reflexion", "max_iterations": 3 }`
- **When** Harness 执行该策略
- **Then** 每轮使用同一个 LLM 客户端和沙箱，结果中的 `strategy` 为 `reflexion`

### Requirement: 失败后先反思再修复

当公共或反馈测试未全部通过时，系统 MUST 先发起一次反思调用，再将反思和可见反馈放入下一轮代码提示。

#### Scenario: 错误解法收敛

- **Given** 第一轮代码未通过可见测试且仍有剩余轮数
- **When** 反思调用成功，随后生成下一轮代码
- **Then** 下一轮提示包含反思内容，最终成功结果包含至少两轮迭代

### Requirement: 隐藏测试隔离

反思和修复提示 MUST 只能包含题目描述、公共测试、反馈测试结果和候选代码，绝不能包含隐藏测试输入或期望输出。

#### Scenario: 隐藏样例不泄露

- **Given** 题目同时配置了公共测试和隐藏测试
- **When** Reflexion 运行失败修复循环
- **Then** 所有模型调用提示均不包含隐藏测试内容

### Requirement: 有界上下文和审计记录

系统 MUST 限制反思日志长度（默认 6000 字符，可配置），并把每次反思的文本、错误、Token、usage 缺失和定价信息写入对应的 `IterationResult` 与 trace。

#### Scenario: 反思日志截断

- **Given** 模型返回超过配置上限的反思
- **When** 生成下一轮提示
- **Then** 提示中的反思日志不超过该上限且保留最新内容

### Requirement: 预算和异常安全

反思调用 MUST 经过现有预算客户端。反思调用触发预算停止时，执行结果 MUST 为 `budget_exhausted`；普通反思异常 MUST 记录并允许策略使用空反思继续修复。

#### Scenario: 反思调用耗尽预算

- **Given** 当前题目的下一次模型调用不再满足预算
- **When** 反思调用被预算客户端拒绝
- **Then** 不执行额外模型调用，结果保留已完成迭代并标记为 `budget_exhausted`
