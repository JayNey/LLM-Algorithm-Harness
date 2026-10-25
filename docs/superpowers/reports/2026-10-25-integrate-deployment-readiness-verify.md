# 部署与监控就绪接入验证

日期：2026-10-25。Change：integrate-deployment-readiness。
分支：comet/integrate-deployment-readiness。基线：e700646797712357fb215e2630f8c6e03710caec。

结论：PASS，无待修复项或待接受偏差。

## 完整性与范围

2/2 tasks 完成。仅一个 deployment delta，1 个 requirement、5 个场景。5 个实现/文档/测试文件，其他均为 Comet/OpenSpec 产物；未引入 public API、schema 或跨层架构协调，无升级信号。tweak 按预设不生成独立 Superpowers Design Doc/plan，以 change/design.md 对照。scale 因含工作流产物的文件数选择 full，按完整规格一致性验证。

## 正确性与一致性

- WebSocket 升级：真实 nginx 测试验证准入前访问就绪接口，准入后保留 Upgrade/Connection 并返回 101。
- 业务限流：原 auth_limit/api_limit 配置保留；探针不参与限流，连续 70 次存活与就绪请求均成功。原部署回归同时检查限流配置与 WebSocket 配置。
- 未就绪关闭准入：数据库/API 就绪失败由既有 API 行为测试覆盖；代理测试验证就绪 503/401/403/500、超时均阻断业务、新握手并返回 503/no-store。探针与管理员诊断独立于准入。连接不可达的 502 按 auth_request 同类错误路径关闭准入，未独立注入真实网络故障。
- 恢复：受控上游从 503 恢复 200 后业务请求自动恢复。业务原有 401/403/500 不重写。探针固定 GET、不携带客户端凭据、请求体或查询参数。
- 告警：文档提供仅认 200、禁用重定向的 blackbox 模块、scrape 配置及持续失败/采集失联两条规则，全部 YAML 示例已解析。未运行 Prometheus 或 Alertmanager，不声称通知已投递。

proposal、design、delta 和实现一致，无 Spec 漂移。镜像 /api/v1/health HEALTHCHECK 未改；生产 nginx 准入使用 /api/v1/health/ready。管理员身份仍由 API 校验。

## 验证证据

- RED：改动前真实 nginx 测试 9 failed、3 passed，证明缺少业务准入和探针限流豁免；依据完整错误和配置定位共同根因后实现。
- GREEN：真实 nginx 回归 13 passed，包含补充的 WebSocket 101 测试；nginx 1.31.8，由 Homebrew 安装，不启用系统服务，仅在测试期间监听本机随机端口。
- 构建/格式：python3 -m compileall -q tests/test_deployment_readiness.py；black --check、ruff check 与 git diff --check 均退出 0。配置改动无独立应用编译目标，真实 nginx 启动验证配置语法及模块可用性。
- 规格：comet classic openspec -- validate integrate-deployment-readiness --strict 退出 0。
- 完整相关回归：python3 -m pytest tests/test_deployment_readiness.py tests/test_deployment_config.py tests/test_api_readiness.py tests/test_api_monitoring.py -q --no-cov：141 passed，21 warnings，46.11s，exit 0。

## 最终集成审查

按 requesting-code-review 使用独立 reviewer 审查 e700646..d822e0d 全部改动及测试，无 actionable findings。明确不判断的范围已核对：既有 WebSocket 转发头继承行为未更改；多 API 副本按文档要求由负载均衡器逐实例检查；Docker/生产集成不在本机实际验证范围内。三项均无当前实现缺陷，不构成待接受偏差。

## 实际边界

Docker daemon 未启动，没有容器构建或生产联调。全仓测试未运行，采用部署/API 就绪及监控的定向回归。现有 Pydantic、SQLAlchemy、pytest 弃用警告保留。基础 API 就绪只反映数据库与迁移；异步 broker、worker、沙箱及模型可用性仍需单独验证。存量 WebSocket 不主动断开，API 自身 1 秒缓存窗口仍有效。外部监控配置需部署方接入现有服务与通知路由。

验证阶段 branch_status 保持 pending。用户随后选择 C：确认归档、立即推送并创建 PR。Comet 归档已成功（6/6 步），主 deployment spec 已按 delta 更新，change 移至 openspec/changes/archive/2026-10-25-integrate-deployment-readiness/，最终归档守卫 6 项通过。branch_status=handled 表示已确认交付方式，推送和 PR 创建结果以交付操作为准。
