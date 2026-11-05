## MODIFIED Requirements

### Requirement: 每题预算控制与停止

系统 SHALL 为每道题支持调用数 / token / 耗时三类预算，达到预算后不再发起模型调用，并记录停止原因与实际消耗。

#### Scenario: 调用数预算耗尽

- **WHEN** 某题的预算为 3 次调用且第 3 次调用后仍未通过
- **THEN** 系统不再为该题发起新调用，该题记录停止原因 `budget_exhausted` 与已发生的调用数、token 与耗时

#### Scenario: token 预算按已知用量结算

- **WHEN** 某题的 token 预算在多轮执行中被累计用量耗尽
- **THEN** 系统在发起下一次调用前停止，累计值包含输入、输出及供应商返回的推理 token

#### Scenario: 供应商无用量数据时标注不支持硬 token 预算

- **WHEN** 模型响应不包含 usage 数据且实验声明了硬 token 预算
- **THEN** 系统在实验记录中标注该组合 `token_budget_unsupported`，不得宣称满足严格 token 预算

调用数 SHALL 按预算包装器准入的逻辑 generate 调用计数：失败及缓存命中均占一次名额，响应结算不得重复增加。内部 SDK 重试属于一次逻辑调用，实际 SDK attempts 由客户端重试配置单独限制；max_calls 不承诺远程请求数或收费上限。

#### Scenario: 首次调用失败后预算耗尽

- **WHEN** max_calls=1 且首次准入调用抛出 provider 异常，策略继续尝试
- **THEN** ledger.calls 为 1，下一次在进入 inner 前抛出 BudgetExhausted，停止原因为 budget_exhausted: max_calls

#### Scenario: 成功与缓存命中不重复计数

- **WHEN** max_calls=1 且首次调用成功或返回缓存响应
- **THEN** ledger.calls 恰为 1，token 按响应结算，第二次调用不进入 inner

#### Scenario: SDK 重试按逻辑调用计数

- **WHEN** 一次准入调用内部执行多个有界 SDK attempts
- **THEN** ledger.calls 为 1，下一次逻辑调用遵守 max_calls 上限

#### Scenario: 多候选策略保留预算终态

- **WHEN** Self-Consistency 在 provider 失败后继续生成候选并遇到预算耗尽
- **THEN** 立即停止候选生成，保留已有迭代，结果 status 为 budget_exhausted，failure_category 为空，ledger 停止原因可审计
