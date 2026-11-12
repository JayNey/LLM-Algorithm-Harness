# execution-protocol Specification

## Purpose
定义 Host 与 Docker 函数返回结果通道的完整性和标准输出隔离要求，明确结果标记缺失、标记不匹配及非法 JSON 的失败语义，并保持 legacy 解析与 stdin/stdout 题目的各自契约，防止提前正常退出的候选程序产生判题假阳性。

## Requirements

### Requirement: 显式函数结果通道必须完整
系统 MUST 使用独立结果通道解析函数返回值，函数向 stdout 打印调试信息不得破坏结果解析。Host 和 Docker function 路径显式请求 result_marker 时 MUST 仅接受匹配该 marker 的合法 JSON payload；缺失或非法时 MUST 返回 runtime_error，且不得接受 stdout 代替返回值。仅未请求显式 marker 的 legacy 解析调用 MAY 回退到 JSON stdout。stdin/stdout 题仍 SHALL 按题目协议比较 stdout。

#### Scenario: 函数打印调试信息
- **WHEN** solution 返回合法值并打印调试信息
- **THEN** 判题只比较 marker 中的函数返回值

#### Scenario: 打印期望值后提前退出
- **WHEN** function 候选打印期望 JSON 并 SystemExit(0)，未产生本次 marker
- **THEN** Host 和 Docker 均返回 runtime_error 且 all_passed 为 false

#### Scenario: 非法结果 payload
- **WHEN** 本次 marker 后的 payload 非法，即使 stdout 是合法期望 JSON
- **THEN** 返回 runtime_error 且不回退 stdout

#### Scenario: 错误 marker
- **WHEN** stderr 只有默认或另一次执行的 marker
- **THEN** 显式请求本次 marker 的调用失败

#### Scenario: 明确 legacy 兼容
- **WHEN** 解析调用未提供显式 marker 且无默认 marker
- **THEN** 允许解析合法 stdout JSON

#### Scenario: 标准输入输出兼容
- **WHEN** 题目使用 stdin_stdout 并打印正确答案
- **THEN** 按原有输出规则判题成功，无需函数 marker

### Requirement: 零测试用例题目不可评估

CLI 和 Web SHALL 在策略求解前识别公开、反馈、隐藏用例均为空的题。每个对应单元 SHALL 产生 `not_evaluable` 结果，记录缺少测试用例的原因，并从成功数、模型失败数及已评估通过率分母中排除。

#### Scenario: 多策略评估缺少测试用例的导入题

- **WHEN** 一道待补全的导入题缺少全部测试用例且使用多个策略评估
- **THEN** 每个策略均保留一个 `not_evaluable` 明细，且无需请求模型或执行候选代码

#### Scenario: 仅有隐藏用例或反馈用例

- **WHEN** 一道题只有隐藏用例或只有反馈用例
- **THEN** 系统仍按对应判题阶段运行用例并保留执行结果
