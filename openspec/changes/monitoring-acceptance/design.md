## 范围与方案
- 基线0e795e4已合入PR269，无重复配置接口实现；逐项映射#157健康/状态/日志/性能/配额/配置及集成、安全、验收标准。
- pending_issues是旧能力交付标记，不是在线GitHub查询。既有必需代码已具备后返回空数组，保持字段和scope兼容；运维失败/禁用仍由checks及总体partial/degraded表达，real_evaluation_available保持unknown/null。
- 新HTTP回归先在已配置数据库正常/不可用、队列关闭两场景复现旧pending断言，再修正单点数据及OpenAPI例子。不修改公开liveness、不增加探测、不改变认证/过滤/限流/统计逻辑。
- 文档删除“仍未实现”的旧结论，列明实际指标来源、用户SDK尝试额度语义、统一生效配置以及API进程/回复worker/当前Docker context的边界。
- 实际Docker opt-in使用既有集成测试；Redis独立临时容器、solo worker只读广播，不提交业务任务或调用LLM。只清理本轮创建资源。失败必须记录原状态，不能跳过后声称通过。

## 验证
监控全簇、worker日志/LLM采集、用户调用/并发额度及HTTP文档/版本兼容定向回归；Ruff/Black/构建、OpenSpec strict与独立Bugbot。报告区分离线HTTP/实际SQLite、真实Docker、真实Redis/Celery与未执行的真实提供商/生产集群/PostgreSQL/Windows Docker。验收只按可复现证据，平台CI只采用当前头结果。

实际依赖验证提供仓库内显式opt-in脚本scripts/verify_monitoring_acceptance.py，输出仅脱敏JSON，私有日志留临时目录；临时Redis带本轮所有权标签，清理前验证，worker与存储依次清理。脚本错误/未确认清理均为失败。
