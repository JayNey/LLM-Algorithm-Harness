# api/system-config Specification

## Purpose
为管理员提供当前 API 进程已加载配置的统一只读视图，以显式字段白名单限制输出，帮助排查部署行为并防止凭据、身份列表及敏感部署路径泄露。

## Requirements

### Requirement: 统一生效配置查询
系统 SHALL 提供 `GET /api/v1/system/config`，返回标准响应信封，data 包含 `scope: api_process` 和 `api`、`auth`、`files`、`monitoring` 四组配置。系统 MUST 从当前服务使用的已加载对象读取配置，不重新读取配置文件或环境变量，不执行数据库、Redis、Docker 或供应商探测。

#### Scenario: 查看已加载配置
- **WHEN** 管理员查询且服务通过环境变量或构造参数覆盖了默认配置
- **THEN** 响应为 200 且返回已加载的覆盖值，后续环境变量变化不改变已加载配置

### Requirement: 显式白名单防泄露
系统 MUST 仅返回经过审核的数值、布尔和可空数值配置字段。凭据、密钥、数据库及消息队列连接串、主机地址、CORS 来源、管理员 ID 列表、文件路径及未知扩展字段 MUST 不出现在响应中；不返回其原文或部分掩码。

#### Scenario: 敏感配置与未知字段
- **WHEN** 已加载配置包含秘密、绝对路径或新增加的非白名单字段
- **THEN** 查询响应只包含白名单字段，且不包含这些敏感值及字段

### Requirement: 管理员认证与禁用缓存
系统 MUST 沿用现有服务端管理员身份判定并对响应设置 `Cache-Control: no-store`。

#### Scenario: 未登录或普通用户
- **WHEN** 未登录用户或已登录普通用户请求配置
- **THEN** 分别返回 401 或 403，不返回配置

#### Scenario: 管理员被撤权
- **WHEN** 管理员身份已从服务端配置撤销后再次查询
- **THEN** 返回 403，不返回配置

### Requirement: 模型目录来源与统一查询
系统 SHALL 在现有 GET /api/v1/config/providers 区分静态支持示例与本人密钥动态模型。两类响应 SHALL 返回 providers 数组、source、scope、live_provider_availability_checked。无 api_key_id 时 SHALL 返回 source=static_examples、scope=offline_example_catalog、live_provider_availability_checked=false，只读取公开固定示例，不暗示完整模型支持清单。提供非空 api_key_id 时 SHALL 返回 source=provider_api、scope=user_api_key、live_provider_availability_checked=true，数组只包含该供应商的 provider、models、complete。评测模型接口 SHALL 使用相同动态 source/scope。

#### Scenario: 默认离线查询
- **WHEN** 管理员不传 api_key_id 查询
- **THEN** 返回静态来源，不查询供应商或读取私有运行配置

#### Scenario: 动态查询
- **WHEN** 管理员传入本人有效密钥
- **THEN** 返回动态列表及 complete，来源与评测接口一致，响应 no-store；枚举成功不保证推理可用

#### Scenario: 权限隔离
- **WHEN** 查询他人、已删除、不存在的密钥，或未登录、普通用户访问
- **THEN** 分别返回 404、401、403，不调用供应商

#### Scenario: 失败和截断
- **WHEN** 供应商失败、密钥并发变化、限流或分页截断
- **THEN** 保留脱敏 503、409、429 或 complete=false，不回退静态；沿用既有超时、500 模型上限、客户端关闭

#### Scenario: 空密钥参数
- **WHEN** api_key_id 是空字符串
- **THEN** 返回 400，不静默返回静态目录
