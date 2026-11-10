## ADDED Requirements

### Requirement: 基准运行默认策略

系统 SHALL 在基准运行的策略字段省略或为空数组时使用单一 `vanilla` 策略。系统 SHALL 保留显式指定的非空策略及其参数。执行时 SHALL 对缺少策略或策略为空的已排队记录应用相同默认值。

#### Scenario: 省略或留空策略

- **WHEN** 创建基准运行时省略 `strategies` 或传入空数组
- **THEN** worker 使用 `vanilla` 执行运行

#### Scenario: 显式策略及参数

- **WHEN** 创建基准运行时指定一个或多个策略
- **THEN** worker 按指定策略及其参数执行

#### Scenario: 旧记录中的空策略

- **WHEN** worker 领取已排队且策略缺失或为空的基准运行
- **THEN** worker 使用 `vanilla` 执行该运行
