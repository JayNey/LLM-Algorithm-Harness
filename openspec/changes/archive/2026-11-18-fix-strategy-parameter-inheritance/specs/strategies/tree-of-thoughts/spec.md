## ADDED Requirements

### Requirement: 搜索控制配置经生产工厂生效

ToT SHALL 从策略 custom_params 接受 branching_factor、max_depth、search_strategy、pruning_threshold，经生产 Harness 工厂创建后按该配置执行。未提供控制值 SHALL 使用既有默认值；显式构造器覆盖值 SHALL 保持优先。分支数和深度 MUST 为非布尔正整数，搜索方式 MUST 为 bfs 或 dfs，剪枝阈值 MUST 为有限的非布尔数且位于闭区间 [0,1]。非法配置 MUST 在供应商调用前失败。

#### Scenario: 工厂传递搜索配置
- **WHEN** 从 Harness 创建 ToT，custom_params 设置 max_depth=1、branching_factor=1、search_strategy=dfs、pruning_threshold=0.9
- **THEN** 实例和实际搜索均使用这四个值，不能回落至 4、3、bfs、0.3

#### Scenario: 默认值和直接构造兼容
- **WHEN** 未配置搜索字段，或直接构造时显式提供覆盖值
- **THEN** 未配置时使用既有默认值，显式构造器值保持生效

#### Scenario: 非法搜索设置
- **WHEN** 任一搜索参数类型不符、分支数或深度小于 1、搜索方式非法、阈值越界或非有限数
- **THEN** 在供应商调用前返回包含字段信息的配置错误

### Requirement: 搜索控制字段不发送供应商

系统 MUST 在供应商请求构建和有效生成参数解析前移除四个 ToT 搜索控制字段，保留合法供应商自定义参数，并继续在策略端使用搜索设置。

#### Scenario: 混合搜索字段和供应商参数
- **WHEN** ToT 配置同时包含四个搜索控制字段与 top_p 等供应商参数，并执行真实客户端的模拟 SDK 调用
- **THEN** SDK 请求与有效生成参数记录均不含搜索控制字段，合法供应商参数继续生效，搜索本身使用配置值
