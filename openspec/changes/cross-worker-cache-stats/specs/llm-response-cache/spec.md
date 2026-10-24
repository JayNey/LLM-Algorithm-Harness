## MODIFIED Requirements

### Requirement: 实际缓存监控采集
系统 SHALL 将真实 LLMClient 使用的缓存命中、未命中及容量快照接入现有管理员缓存统计接口，跨 worker/API 进程共享；采集失败 SHALL NOT 改变生成结果。计数 SHALL 明确保留实例快照口径，容量 SHALL 按缓存存储目录去重并标明采样年龄，陈旧容量 SHALL NOT 冒充实时值。采集与输出 SHALL 仅包含白名单数字及不可逆内部身份，不包含路径、缓存键、提示、响应或凭据。

#### Scenario: 真实命中与未命中
- **WHEN** 实际客户端首次请求未命中并写入缓存，随后相同请求命中
- **THEN** 管理员读取到一次 miss 和一次 hit、实际磁盘容量，SDK 只调用一次

#### Scenario: 跨进程和共享目录
- **WHEN** 多个客户端或 worker 共用监控存储且同一主机目录被重复采样
- **THEN** API 可读取统计，重复快照不重复累计计数，同一目录容量只计一次

#### Scenario: 不可用或陈旧
- **WHEN** 没有观测、缓存禁用、容量采样超过 300 秒或采集失败
- **THEN** 系统明确报告相应状态，不伪造命中率/实时容量，生成行为不受采集失败影响

系统 SHALL 分别汇总成功上报且仍保留的不同 Worker 实例快照中的 hits 与 misses，整体命中率 SHALL 为 sum(hits)/(sum(hits)+sum(misses))，不得对实例命中率取算术平均。分母为零 SHALL 返回 null；未启用缓存的调用不构成缓存查询。指标 SHALL 保留实例生命周期快照口径及 cluster_complete=false，不得冒充全群集累计或保留时间窗口内的请求统计。

#### Scenario: 不同 Worker 请求量不均
- **WHEN** 两个 Worker 分别上报 hits=9, misses=1 与 hits=0, misses=90
- **THEN** 汇总 hits=9、misses=91，整体命中率为 0.09

#### Scenario: 重复更新与过期退出
- **WHEN** 同一实例重复上报或更新累计快照，或某实例快照超过保留期限
- **THEN** 每个保留实例只使用最新快照一次，过期实例不参与分子和分母

#### Scenario: 零请求
- **WHEN** 保留观测中没有缓存命中或未命中
- **THEN** hits 与 misses 为零且整体命中率为 null
