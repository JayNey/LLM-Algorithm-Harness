## ADDED Requirements

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
