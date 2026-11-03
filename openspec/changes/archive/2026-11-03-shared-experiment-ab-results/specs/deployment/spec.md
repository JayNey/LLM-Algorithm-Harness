## MODIFIED Requirements

### Requirement: 容器化交付

系统 SHALL 提供生产级 API 镜像与 Worker 镜像：两镜像均 SHALL 以多阶段构建产出，并以非 root 用户运行；API 镜像 SHALL 内置对 `/api/v1/health` 的健康检查；Worker 镜像 SHALL 包含沙箱预检所需的 docker CLI；两镜像 SHALL 创建供非 root 用户写入的 `/app/results` 目录。

#### Scenario: API 镜像自检通过

- **WHEN** 按镜像默认入口启动 API 容器且依赖服务可用
- **THEN** 容器内置健康检查对 `/api/v1/health` 探测成功，进程以非 root 用户运行

#### Scenario: Worker 镜像具备沙箱预检条件

- **WHEN** 进入 Worker 容器执行沙箱预检所依赖的 docker 命令
- **THEN** docker CLI 存在且命令可被调用（连接结果取决于是否挂载宿主 socket）

#### Scenario: 非 root 用户可写结果目录

- **WHEN** 以镜像默认用户向 `/app/results` 写入文件
- **THEN** 目录已由 `harness` 用户拥有，写入成功

### Requirement: 一键编排

系统 SHALL 提供开发与生产两套 compose 编排：开发编排 SHALL 包含 postgres、redis、api、worker、beat，并保持既有 `redis` 服务名、端口与健康检查不变以兼容集成测试脚本；生产编排 SHALL 包含 postgres、redis、api、worker、beat、nginx，服务 SHALL 配置 `restart: unless-stopped` 与健康检查，数据 SHALL 落在命名卷，且生产编排 SHALL NOT 以绑定挂载方式引入源码目录。两套编排 SHALL 为 api 与 worker 挂载同一命名结果卷到相同的 `/app/results` 路径，保证实验与 A/B 的产物和检查点跨进程可读。

#### Scenario: 集成测试仅启动 redis

- **WHEN** 开发者执行 `docker compose up -d redis` 后运行集成测试脚本
- **THEN** redis 服务以原有端口与健康检查启动，集成测试可正常连接

#### Scenario: 生产栈整体拉起

- **WHEN** 部署者以生产编排文件启动全栈
- **THEN** postgres、redis、api、worker、beat、nginx 全部启动并带重启策略，源码目录未以绑定挂载进入任何容器

#### Scenario: 结果卷跨服务共享

- **WHEN** 检查两套编排的 api 与 worker 服务
- **THEN** 两者都挂载同一个 `results_data` 命名卷到 `/app/results`，顶层 volumes 声明该卷

### Requirement: 环境配置样例与校验

系统 SHALL 提供覆盖应用全部配置项的 `.env.example`，按用途分组并附注释；`.env.example` 中 SHALL NOT 出现真实密钥。生产模式下缺失安全必需配置（如认证密钥）时，应用 SHALL 在启动校验中失败并指明缺失的变量名，不得以不安全默认值静默启动。结果根 `RESULTS_ROOT` SHALL 出现在样例中；应用与 Worker SHALL 在启动时校验其可创建且可写，不可写时立即失败并报告路径。

#### Scenario: 样例与配置字段一致

- **WHEN** 对比 `.env.example` 与应用 Settings 的字段集
- **THEN** 每个可配置字段在样例中有对应条目或显式注释说明

#### Scenario: 生产缺失必需密钥时拒绝启动

- **WHEN** 以生产模式启动应用且未提供安全必需配置
- **THEN** 启动校验失败并指明缺失的变量名

#### Scenario: 结果根不可写时拒绝启动

- **WHEN** 启动时 `RESULTS_ROOT` 指向不可创建或只读的位置
- **THEN** 进程以包含该路径的明确错误退出，不开始处理任务
