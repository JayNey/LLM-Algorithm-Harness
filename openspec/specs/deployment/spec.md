# deployment Specification

## Purpose
规定 API 与 Worker 的容器化交付、环境配置、编排、反向代理、健康探针与业务就绪准入，以及部署日志、迁移和种子数据的验收要求。

## Requirements

### Requirement: 容器化交付

系统 SHALL 提供生产级 API 镜像与 Worker 镜像：两镜像均 SHALL 以多阶段构建产出，并以非 root 用户运行；API 镜像 SHALL 内置对 `/api/v1/health` 的健康检查；Worker 镜像 SHALL 包含沙箱预检所需的 docker CLI。

#### Scenario: API 镜像自检通过

- **WHEN** 按镜像默认入口启动 API 容器且依赖服务可用
- **THEN** 容器内置健康检查对 `/api/v1/health` 探测成功，进程以非 root 用户运行

#### Scenario: Worker 镜像具备沙箱预检条件

- **WHEN** 进入 Worker 容器执行沙箱预检所依赖的 docker 命令
- **THEN** docker CLI 存在且命令可被调用（连接结果取决于是否挂载宿主 socket）

### Requirement: 一键编排

系统 SHALL 提供开发与生产两套 compose 编排：开发编排 SHALL 包含 postgres、redis、api、worker、beat，并保持既有 `redis` 服务名、端口与健康检查不变以兼容集成测试脚本；生产编排 SHALL 包含 postgres、redis、api、worker、beat、nginx，服务 SHALL 配置 `restart: unless-stopped` 与健康检查，数据 SHALL 落在命名卷，且生产编排 SHALL NOT 以绑定挂载方式引入源码目录。

#### Scenario: 集成测试仅启动 redis

- **WHEN** 开发者执行 `docker compose up -d redis` 后运行集成测试脚本
- **THEN** redis 服务以原有端口与健康检查启动，集成测试可正常连接

#### Scenario: 生产栈整体拉起

- **WHEN** 部署者以生产编排文件启动全栈
- **THEN** postgres、redis、api、worker、beat、nginx 全部启动并带重启策略，源码目录未以绑定挂载进入任何容器

### Requirement: 反向代理

系统 SHALL 提供 nginx 配置：将请求反代至 api 服务，启用 gzip，对 API 路径按来源限流，为 `/api/v1/ws` 提供 WebSocket 升级代理，并 SHALL 给出 HTTPS 启用的注释模板；请求体上限 SHALL 与上传服务的上限对齐。业务请求及 WebSocket 握手 SHALL 在就绪接口 `/api/v1/health/ready` 成功后才准入；就绪失败、异常或超时 SHALL 返回 503。存活探针 SHALL 继续使用 `/api/v1/health`；健康接口与管理员诊断 SHALL 不受就绪准入或业务限流阻断。业务可用性告警 SHALL 以就绪接口 HTTP 200 为成功条件，而非存活或管理员诊断响应。

#### Scenario: WebSocket 经代理升级
- **WHEN** API 就绪且客户端经 nginx 对 `/api/v1/ws` 发起 WebSocket 升级请求
- **THEN** nginx 附加 Upgrade 与 Connection 头将连接代理至 api，连接保持长连

#### Scenario: 超限请求被限流
- **WHEN** 同一来源在限流窗口内对业务 API 路径发起超过阈值的请求
- **THEN** 超出部分收到限流错误响应，服务后端不被直接打穿

#### Scenario: 未就绪关闭业务准入
- **WHEN** 就绪接口返回 503、不可达或超时
- **THEN** nginx 不转发业务请求与新 WebSocket 握手，返回 503，存活与诊断路径仍可访问

#### Scenario: 恢复准入
- **WHEN** 就绪接口重新返回 200
- **THEN** 后续业务请求可通过准入，应用自身错误状态保持原样

#### Scenario: 可用性监控
- **WHEN** 就绪接口失败或超时且存活接口仍为 200
- **THEN** 业务可用性监控判定失败，存活监控继续成功，告警示例覆盖此情形

### Requirement: 环境配置样例与校验

系统 SHALL 提供覆盖应用全部配置项的 `.env.example`，按用途分组并附注释；`.env.example` 中 SHALL NOT 出现真实密钥。生产模式下缺失安全必需配置（如认证密钥）时，应用 SHALL 在启动校验中失败并指明缺失的变量名，不得以不安全默认值静默启动。

#### Scenario: 样例与配置字段一致

- **WHEN** 对比 `.env.example` 与应用 Settings 的字段集
- **THEN** 每个可配置字段在样例中有对应条目或显式注释说明

#### Scenario: 生产缺失必需密钥时拒绝启动

- **WHEN** 以生产模式启动应用且未提供安全必需配置
- **THEN** 启动校验失败并指明缺失的变量名

### Requirement: 结构化日志

系统 SHALL 支持 `LOG_LEVEL` 与 `LOG_FORMAT` 配置：`LOG_FORMAT=json` 时应用与 uvicorn 日志 SHALL 以 JSON 结构化输出；默认 SHALL 保持人类可读格式。切换格式 SHALL NOT 需要修改代码。

#### Scenario: 生产 JSON 日志

- **WHEN** 以 `LOG_FORMAT=json` 启动应用并产生请求日志
- **THEN** 日志行可被 JSON 解析，级别由 `LOG_LEVEL` 控制

### Requirement: 数据迁移与种子数据

系统 SHALL 在应用启动时自动执行业务库迁移（既有能力，保持不变），并 SHALL 提供幂等的种子数据脚本：重复执行 SHALL NOT 产生重复数据；迁移回滚路径 SHALL 写入部署文档。

#### Scenario: 种子脚本幂等

- **WHEN** 对同一数据库连续两次执行种子脚本
- **THEN** 第二次执行不新增重复记录且正常退出
