## ADDED Requirements

### Requirement: 策略生成参数持久化保留显式性

系统 SHALL 在实验、A/B 和基准的策略配置保存、加载和执行中保留省略字段与显式值的区别。省略的 temperature 和 max_tokens SHALL 继承模型配置，显式策略值 SHALL 优先，包括恰等于策略默认值的输入。历史记录中已存字段 SHALL 继续作为显式值解释，不猜测并删除默认值。

#### Scenario: 真实数据库往返保留继承
- **WHEN** 模型温度为 0.2，策略省略 temperature 和 max_tokens，经三类业务的真实数据库保存和加载
- **THEN** 执行时策略继承温度 0.2 与模型的 max_tokens，省略字段不被补成显式默认值

#### Scenario: 显式默认值优先
- **WHEN** 模型温度为 0.2 且模型 max_tokens 不为 2000，策略显式填写 temperature=0.7 和 max_tokens=2000 后保存并加载
- **THEN** 执行请求使用温度 0.7 和 max_tokens=2000

#### Scenario: 默认配置往返和历史记录
- **WHEN** 默认策略省略覆盖值，或加载历史记录中已保存的 temperature=0.7 与 max_tokens=2000
- **THEN** 前者往返保留继承语义，后者保留显式旧值，兼容说明告知用户可重新保存以恢复继承
