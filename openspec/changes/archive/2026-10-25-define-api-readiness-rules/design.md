## Context

`api/main.py` 的公开 `/health` 只表示存活。`api/monitoring/service.py` 的管理员诊断聚合数据库、Redis、worker 和可选沙箱观测；`partial`、`degraded`、`healthy` 均不是准入结论。数据库探测覆盖认证/文件 SQLite 以及业务库表与迁移；队列探测默认可关闭，沙箱预检默认不执行。

## Goals / Non-Goals

目标是定义依赖对不同业务能力的影响与未知状态的处理，并以文档示例作为后续实现的验收输入。

不实现 `/health/ready`、中间件或路由闸门，不改变现有诊断状态、HTTP 响应、监控配置或启动流程。

## Decisions

- 基础 API 就绪要求当前 API 使用的认证、文件及业务数据库全部通过连接与所需 schema 检查，业务迁移匹配。Redis、worker、沙箱故障不剔除仍能提供基础业务服务的 API 实例。
- 异步任务提交另要求配置的 broker 可用；worker 暂时离线仍可接受已可靠入队的任务，不承诺立即执行。Redis PING 仅是 broker 连通性证据，提交成功还需实际持久化与消息投递成功。
- 后台执行能力单独观察 worker 与实际执行环境的沙箱；API 本机 Docker 成功不证明 worker 的沙箱可用。
- 未检查、禁用、未知、超时、过期、范围不符都不是成功；只阻塞依赖该证据的能力，不能把未检查改写成故障或把不相关依赖变成全局准入条件。
- 现有管理员诊断与后续 readiness 的鉴权、响应格式分别处理。本次不指定尚未实现的 HTTP 契约或新增监控参数。

## Risks / Trade-offs

- 基础 API 就绪不保证任务可提交或执行 → 文档分别写明三种范围，禁止用基础就绪宣称完整评估链路可用。
- 文档先于实现 → 显著保留 readiness 未实现、404、不可配置为部署探针的说明，并说明规则不会自动拦截现有业务请求。

## Verification

检查依赖规则、未知状态、边界场景、文档链接及未实现声明；运行现有健康接口与部署契约测试，确认本次不改变已发布行为。文档无独立编译或格式化命令，以 `git diff --check` 和 OpenSpec strict validate 验证。无 delta spec，无独立 Superpowers Design Doc。
