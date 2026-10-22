## ADDED Requirements

### Requirement: 标签范围内的管理员只读观测
系统 SHALL 默认关闭容器资源观测，仅管理员可显式启用，且仅查询固定管理标签的运行容器。

#### Scenario: 禁用或无权限
- **WHEN** 配置未启用，或请求为公开健康/无身份/非管理员
- **THEN** 不执行任何 Docker 容器采样命令

#### Scenario: 存在其他容器
- **WHEN** 当前 Docker context 同时存在有标签和无标签容器
- **THEN** 仅返回所选有标签沙箱的匿名 ID 与资源数值，不返回原始名称/配置或操作其他容器

### Requirement: 有限且准确的快照
采样 SHALL 共享时间预算，限制输出和样本量；明确非原子、非完整集群与 CLI 数值语义。

#### Scenario: 空、缺失和非法测量
- **WHEN** 成功列表为空，或部分容器已退出/字段不可用
- **THEN** 分别返回范围内真实空列表，或 partial/null，不把失败和缺测伪造成零

#### Scenario: 超时、异常和过量输出
- **WHEN** Docker 卡住、失败或输出超限
- **THEN** 终止并回收命令进程树，返回固定安全原因，不泄露 stdout/stderr 或路径

### Requirement: 生命周期与缓存
同一 API 进程 SHALL 去重并发探测，缓存成功和失败并标记年龄，关闭后拒绝新采样。

#### Scenario: 并发和过期
- **WHEN** 缓存过期且已有一个采样进行中
- **THEN** 新请求得到 refresh_in_progress，旧成功值不作为新测量返回

#### Scenario: 关闭
- **WHEN** 服务关闭
- **THEN** 立即拒绝后续读取并在已有命令的有界预算及清理余量内等待结束
