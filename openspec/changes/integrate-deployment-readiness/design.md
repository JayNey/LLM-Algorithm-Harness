## 实现
在 nginx server 层配置 auth_request 子请求，复用公开就绪接口。就绪子请求固定 GET、不转发请求体、凭据或查询参数，超时为 2 秒，禁止代理缓存。auth_request 对非 2xx/401/403 返回内部错误，因此将其产生的 500 映射到命名 location 返回 503/no-store；业务代理保留 proxy_intercept_errors off，业务自身的 500/401/403 不重写。健康接口、管理员 system 接口和内部子请求显式关闭 auth_request，避免递归与诊断被阻断。健康接口不参与业务限流，避免探针收到限流造成误报。

基础 API 就绪只覆盖数据库和迁移，不代表 Redis、worker 或沙箱可用。已建立的 WebSocket 不会被此配置主动断开。单实例 Compose 只做边缘准入，不能自动摘除副本。HTTPS 模板须复用相同准入策略。

## 验证
部署配置回归验证各业务 location 继承准入、探针绕过、超时和无缓存；API 就绪测试验证数据库故障 503、存活仍 200 及恢复。提供 Prometheus blackbox exporter、scrape 和告警的可复制示例，包含探测失败与 exporter 抓取失败。
本机 Docker daemon 未启动；真实代理验证使用临时启动的本机 nginx，不启动系统服务，不声称已完成容器或生产联调。
