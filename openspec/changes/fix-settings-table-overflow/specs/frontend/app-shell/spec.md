## MODIFIED Requirements

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

#### Scenario: 有数据的预算和定价表格

- **WHEN** 用户在 320、390、768、1024 或 1440px 打开有数据的 `/settings/budgets`、`/settings/pricing`，或展开有历史记录的定价抽屉
- **THEN** 预算用量、预警规则与投递历史、费用汇总与趋势及分项、定价目录与历史表格各自位于具名的可聚焦区域内，文档宽度不超过视口
- **AND** 表格超过可用宽度时，用户可以在聚焦的区域内横向滚动，也可以用 Tab 到达表格末列的操作
