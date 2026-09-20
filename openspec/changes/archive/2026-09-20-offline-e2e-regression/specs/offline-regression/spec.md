## Purpose

定义离线端到端回归的覆盖范围、负向场景行为与在线/离线验证的区分要求。

## ADDED Requirements

### Requirement: 离线端到端成功链路
系统 SHALL 在固定响应模型替身下，端到端完成 CLI 运行 → 题库加载 → 策略执行 → 沙箱执行 → 结果文件落盘，且结果文件字段可精确断言。

#### Scenario: 正确答案链路
- **WHEN** 模型替身返回全部用例正确的解法并运行单题评测
- **THEN** summary 与策略结果文件记录 solved=1、`failure_category` 为空、token 汇总准确

### Requirement: 离线端到端失败链路
失败答案链路 MUST 精确记录失败：`failure_category=wrong_answer`、逐用例 actual/expected 保留，不误判为成功。

#### Scenario: 错误答案链路
- **WHEN** 模型替身返回错误解法
- **THEN** 结果文件记录 `failure_category=wrong_answer` 且失败用例的期望/实际输出可查

### Requirement: 负向输入显式失败
缺失数据集、坏配置文件与空策略列表 MUST 以非零退出与明确错误结束，不产生结果文件。

#### Scenario: 缺失数据集
- **WHEN** `--dataset` 指向不存在的文件
- **THEN** 非零退出、错误信息指明数据集缺失、无结果目录产生

#### Scenario: 坏配置文件
- **WHEN** `--config` 指向格式非法的文件
- **THEN** 非零退出并报配置错误

#### Scenario: 空策略列表
- **WHEN** 配置的 `strategies` 为空
- **THEN** 显式报错退出，不产生空报告

### Requirement: 验证记录区分
在线（真实凭证）与离线（替身）验证 MUST 在文档与测试标记中明确区分；默认 CI 不发起外部请求，online 用例跳过状态可见。

#### Scenario: 无凭证运行在线用例
- **WHEN** CI 无 `SILICONFLOW_API_KEY` 运行在线验证文件
- **THEN** 用例跳过且跳过状态在输出中可见

#### Scenario: 文档区分
- **WHEN** 阅读 README 测试章节
- **THEN** 能明确区分替身测试与真实调用验证的运行方式
