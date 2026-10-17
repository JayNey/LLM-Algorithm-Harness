## Purpose

提供可安装、可本地开发和可生产构建的 Web 应用外壳，让后续页面在统一的环境变量、路由和后端代理上开发。

## ADDED Requirements

### Requirement: 本地开发服务器

前端工程 SHALL 能启动本地开发服务器，源码变更后热更新，并将以 `/api` 开头的请求转发到配置的后端 origin。

#### Scenario: 开发服务器转发 API

- **WHEN** 开发服务器正在运行且客户端请求 `/api/v1/health`
- **THEN** 该请求被转发到后端 origin，而不是由前端静态资源处理

### Requirement: 环境配置

前端 SHALL 按开发、测试和生产模式读取 API Base URL、WebSocket URL、应用名称和功能开关。必填地址缺失时 SHALL 失败并指出变量名，不得静默使用空地址。

#### Scenario: 开发模式读取地址

- **WHEN** 以开发模式启动应用
- **THEN** 应用读到该模式配置的 API Base URL、WebSocket URL 和应用名称

#### Scenario: 缺少 API 地址

- **WHEN** 当前模式没有提供 API Base URL
- **THEN** 启动或构建失败，并指出缺失的变量名

### Requirement: 基础导航

应用 SHALL 提供仪表盘、题目、评估、结果、实验和设置六个页面。这些页面在后端不可用时仍可打开。未登记路径 SHALL 回到仪表盘。

#### Scenario: 进入题目页

- **WHEN** 用户打开题目路径
- **THEN** 页面表明当前位于题目，且不请求后端数据

#### Scenario: 未知路径

- **WHEN** 用户打开未登记路径
- **THEN** 应用显示仪表盘

### Requirement: 生产构建

前端 SHALL 能在类型检查通过后生成生产静态资源，并且六个页面按路由分割加载。

#### Scenario: 生产构建成功

- **WHEN** 执行生产构建
- **THEN** 命令成功退出，并产出按路由分割的静态资源

### Requirement: 代码规范

前端 SHALL 提供可重复执行的代码检查和格式校验。提交仅包含前端文件的改动时，钩子 SHALL 只检查暂存的前端文件。

#### Scenario: 初始工程通过检查

- **WHEN** 在初始工程上运行代码检查和格式校验
- **THEN** 两个命令都成功退出

### Requirement: 外观基线

应用外壳 SHALL 支持浅色和深色两套配色，并在窄屏和宽屏下保持六个页面入口可达。

#### Scenario: 切换深色

- **WHEN** 用户切换为深色配色
- **THEN** 外壳使用深色配色，且在同一次浏览中保持该选择

#### Scenario: 窄屏导航

- **WHEN** 视口为移动宽度
- **THEN** 六个页面入口仍然可达
