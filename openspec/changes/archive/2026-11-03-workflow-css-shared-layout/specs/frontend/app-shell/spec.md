## ADDED Requirements

### Requirement: 共享工作流样式随外壳加载

应用 SHALL 在已登录工作台的共享布局中加载工作流样式（列表表格、面板、事实列表、分页与操作区），并随入口样式下发；使用这些类的页面 MUST NOT 再各自导入同一份样式。直接打开或刷新任一工作流页面时，样式 SHALL 与站内导航进入时一致。

#### Scenario: 直接打开实验列表

- **WHEN** 已登录用户直接打开或刷新 `/experiments`
- **THEN** 列表表格呈现折叠边框与 760px 最小宽度，表头与单元格内边距生效，表格在自身滚动容器内横向滚动，页面没有整体横向溢出

#### Scenario: 直接打开其他工作流页面

- **WHEN** 已登录用户直接打开或刷新 `/experiments/new`、`/experiments/:experimentId`、`/ab-tests`、`/ab-tests/new` 或 `/benchmarks/:suiteId`
- **THEN** 面板、事实列表与操作区使用共享工作流样式，页面没有未套用样式的重叠或内容挤压

#### Scenario: 单一导入来源

- **WHEN** 检查前端源码
- **THEN** `workflow.css` 只由共享布局导入，页面组件不再包含该导入

### Requirement: 直接加载视觉 smoke

前端 SHALL 提供可重复执行的浏览器视觉 smoke，针对生产构建直接加载工作流页面，断言共享样式已进入入口 CSS、关键计算样式生效、页面无横向溢出与运行异常，并保存截图与报告。

#### Scenario: 运行 smoke

- **WHEN** 构建产物存在时运行 `node scripts/verify-direct-load.mjs`
- **THEN** 脚本直接加载各工作流路由并全部断言通过，输出截图与报告后以 0 退出；任一断言失败时以非 0 退出
