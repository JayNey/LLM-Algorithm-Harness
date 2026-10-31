# Comet Design Handoff

- Change: benchmark-run-history
- Phase: design
- Mode: compact
- Context hash: 3aa10396e84df899f5bc34ac42d7e124bfa9a40007db47d5dd7b80e3525f92f6

Generated-by: comet-handoff.sh
Task hash policy: task-content-v1. Read tasks.md for live completion; excerpts are design-time context.

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/benchmark-run-history/proposal.md

- Source: openspec/changes/benchmark-run-history/proposal.md
- Lines: 1-27
- SHA256: 85417a3d854c2761a59c6a57d03b2f4f5834e3143b4eabc48d62206aa27297fb

```md
## Why

#322：基准详情仅把新启动任务 ID 保存在组件内存，刷新或重新进入后无法找回运行；后端 #309 已合并历史分页与关联标识，但前端尚未消费。用户需要可靠查询历史、恢复进度并分享同一运行。

## What Changes

- 接入真实运行历史分页、状态筛选、选择和空态/权限错误。
- URL 保存选中 run_id；明确选择的运行直接查询，不依赖当前历史页，失效地址明确反馈。
- 以返回的 task_id 查询进度并校验关联；区分排队、执行、暂停和终态，切换账号、路由或运行时取消旧请求。
- 学习曲线运行可导航，终态更新历史、结果与曲线，保留已有创建表单、模型目录和个人数据集选择。
- 完成中英文、键盘和窄屏验证，以及客户端、页面、真实 HTTP 联调。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/benchmark-management`：增加可刷新和分享的历史导航与进度恢复，学习曲线定位真实运行。

## Impact

影响 frontend/src/benchmarks、BenchmarkDetailPage、图表导航及翻译/验证脚本。复用 #309 后端契约，不重写 B3，不增加全业务任务管理，不改变模型、数据集和套件管理合同。独立于 #319，单独 PR；基线 main@8a6ab918c3f70e38e9c00d4251f9d4343da98120。

关键未知项由设计具体化：无显式 run_id 时的活动运行发现、暂停后手动刷新、实体归属校验和终态刷新策略。验收以刷新恢复、分页外选中运行、并行运行选择、失效 URL、账号隔离与终态停止轮询为核心。

```

## openspec/changes/benchmark-run-history/design.md

- Source: openspec/changes/benchmark-run-history/design.md
- Lines: 1-62
- SHA256: f6ec7a0bd1a97af1d8c7e2925d972b13515fbf8c4b51dd4a021e9ee0f30b634f

```md
---
comet_change: benchmark-run-history
role: technical-design
canonical_spec: openspec
---

## Context

动机见 proposal.md。基线 main@8a6ab91 的后端已提供带 total/limit/offset/has_more 的套件运行历史、单次详情中的 task_id 和曲线点 run_id。前端丢弃部分字段，并仅在组件中记录刚启动的 taskId；useTaskProgress 已支持终态/暂停停止和 AbortSignal，BenchmarkSessionProvider 按账号会话 marker 重建。

本设计是本 change 唯一正式设计文档。语言 zh-CN；用户已选择 URL 恢复方案及独立 PR，本文具体策略为待审阅的实施建议。

## Goals / Non-Goals

Goals：同一个运行在刷新、分享、分页、曲线导航下具有一致身份；结果和进度属于当前套件、账号和选择；保留套件编辑和运行表单。

Non-Goals：增加暂停/恢复服务端操作、重写后端历史、全业务任务管理、替换已有模型目录/数据集选择。

## Decisions

### 1. Approaches 与 URL 合同

用户选择方案 A：在现有 /benchmarks/:suiteId 页面使用 run_id 查询参数持久化选中运行，其他查询参数保留。历史筛选与 offset 使用同一 URL，参数均作白名单/数值校验。点击历史、启动成功或曲线点时设置真实 run_id；改变筛选只重置 offset，不清除明确选中的运行。

方案 B 是 localStorage 保存最新任务；会跨标签页/会话残留且无法分享，不采用。继续仅用组件 state 不满足刷新恢复，不采用。

显示明确 run_id 时直接调用运行详情，不先扫描历史页。验证响应 id 与 URL 一致、suite_id 属于当前套件；task_id 可为空，无任务时展示运行结果及真实说明，不猜测任务 ID。获取任务后验证 task.id、entity_id 和 task_type=benchmark；不符合则停止观察并反馈协议错误，不展示错误进度。

### 2. 历史与活动运行发现

客户端新增强类型 runs(suiteId,{status,limit,offset},signal) 与 task_id/run_id 解析；分页严格使用后端 total/has_more，不从当前页长度推断总数。历史表提供全部/每种真实状态、上一页/下一页、选中运行链接，显示 ID、状态、模型、时间及已有可用指标。

无显式 run_id 时，独立查询 pending、running、paused 三种状态的第一页，作为可选择的活动运行入口，保留每页真实总数及“更多”导航。仅发现一个活动运行且三组查询均成功、总数合计恰为 1 时，通过 replace 写入 URL 自动恢复；多个时展示选择，不自动拿最新 completed 冒充活动运行。活动查询不以 completed 默认页为依据。零个活动运行显示历史选择引导，错误保持可重试而不当作零个。

### 3. 观察生命周期与刷新

详情选择范围以 owner + suiteId + run_id 键控组件/请求。所有查询传 AbortSignal，账号、套件、运行切换和卸载时清理定时器、观察器和在途请求；返回内容再次核对身份。

pending/running 观察关联任务，每 3 秒 HTTP 轮询，不新增 WebSocket。paused 展示保留进度与“刷新运行”操作，停止自动轮询。completed/failed/cancelled 是终态，停止轮询。连续失败显示可重试反馈，不把观察失败当作业务完成；终态刷新详情、历史、活动入口和曲线一次，通过选中运行与终态签名去重，避免刷新循环。手动刷新同时重新获取运行关联和重启需要的进度观察，支持暂停任务已在其他页面恢复后的核对。

终态指标读取运行详情；不以曲线中最新记录替代。启动成功使用响应 run.id 更新 URL，并刷新历史；同步提交锁防止双击，旧页面的异步启动/保存响应不能导航新页面或污染新账号。

### 4. 曲线与界面

曲线点保留后端 run_id，点击可定位对应运行；为键盘和触屏同时提供与图表同源的运行链接列表。复用现有图表能力，扩展事件时保持旧调用兼容。详情展示选中运行状态/错误和准确率、费用；未产生值时显示缺失，不填零。结果详情中提供后端返回的实际结果内容，解析只消费已知字段，不虚构结果行。

复用现有 panel/table/反馈组件；表格在窄屏容器内滚动，页面 320px 无整体横向溢出；新增文案中英文齐全，选择和刷新可键盘操作。保留原编辑、模型策略选项和个人数据集表单。

## Risks / Trade-offs

- 活动运行很多：发现区只载入每状态一页并明确总数/更多，选择全部历史有真实分页，不假装列举全部。
- 后端状态与任务瞬时不同：展示各自来源，任务终态触发详情核对，暂停和观察失败提供手动刷新。
- 未授权或删除的链接：详情 403/404 明确反馈，保持用户 URL，不偷偷改选另一运行。
- 图表点击可访问性不足：保留等价语义链接；共享图表修改需跑原图表回归。

## Validation

先 RED 再 GREEN 验证客户端历史分页/关联字段与 URL 解析、分页外选中运行、失效地址和关联不匹配。页面验证多活动运行、暂停/终态、路由及账号切换旧响应隔离、终态资源刷新和键盘导航。真实 HTTP 联调使用隔离账号、套件/运行与任务记录，明确播种状态边界，不声称调用真实付费模型。检查 npm test、lint、tsc/build，320px 和中英文，独立集成审查。

## Migration Plan

不改数据库和后端接口；前端部署即可。旧无参数地址继续可用。回滚前端代码即可恢复旧详情；不修改服务器运行记录。与 #319 无合入顺序依赖。

```

## openspec/changes/benchmark-run-history/tasks.md

- Source: openspec/changes/benchmark-run-history/tasks.md
- Lines: 1-15
- SHA256: 0aab104d0811f0585ed7f2f3e0c464e040c925403d68e94d878e0ecc9b621872

```md
## 1. 运行合同与导航

- [ ] 1.1 扩展历史分页、任务关联和曲线标识的前端类型/严格解析；通过客户端契约测试验证真实分页参数、空页、可空 task_id、run_id 和非法响应。 <!-- comet-task:e603f607-7f82-4817-9788-63cb2f4a2e4c -->
- [ ] 1.2 实现 URL 查询和运行选择策略；以测试验证刷新恢复、保留其他参数、分页外显式运行、无效 URL 及活动运行唯一/多条选择。 <!-- comet-task:148b7e48-34e7-41f9-bb25-f4c5077e8e59 -->

## 2. 页面与观察

- [ ] 2.1 接入真实历史表、状态筛选/分页、活动运行入口和选中详情；页面回归覆盖空态、403/404、跨套件关联拒绝及原模型/数据集表单保留。 <!-- comet-task:3942f49e-6368-464e-b87e-61329e1b4e45 -->
- [ ] 2.2 实现选中运行关联任务的进度观察、暂停手动刷新、终态资源对账及提交锁；验证终态停止、失败重试、路由/账号变化清理和旧响应隔离。 <!-- comet-task:7d69df2b-10fe-4e86-8d1a-c8a54d5c3891 -->
- [ ] 2.3 接入曲线 run_id 导航和键盘等价链接，补齐双语与窄屏样式；通过曲线选择、键盘和 320px 布局检查。 <!-- comet-task:e32654b0-18a8-41ef-b4ce-b3f6ab44e0df -->

## 3. 综合验收与交付

- [ ] 3.1 完成真实 HTTP 与浏览器联调、前端测试/lint/类型构建和相邻表单回归；交付可复跑脚本及标明播种/替身边界的验证报告。 <!-- comet-task:bb6f51be-9e14-4382-a7e3-379c1396eb96 -->
- [ ] 3.2 完成分段独立审查并修复问题，核对规格和提交归属，备齐独立 PR 交付材料；以实际复审、检查及提交记录验收。 <!-- comet-task:e64054f8-2807-48fd-9e7a-04a51c52acf6 -->

```

## openspec/changes/benchmark-run-history/.openspec.yaml

- Source: openspec/changes/benchmark-run-history/.openspec.yaml
- Lines: 1-2
- SHA256: 108f7b3dae33488206672f31b510275110c0194c93062eb1970e19ca60c08722

```md
schema: spec-driven
created: 2026-11-01

```

## openspec/changes/benchmark-run-history/specs/frontend/benchmark-management/spec.md

- Source: openspec/changes/benchmark-run-history/specs/frontend/benchmark-management/spec.md
- Lines: 1-69
- SHA256: df380b203da26c4b333c3815b138cab53f3bd0a3d34007fa74021d6971cb4375

```md
## MODIFIED Requirements

### Requirement: 基准 Suite 管理

前端 SHALL 提供基准 Suite 的列表（全量返回，不伪造分页参数）、创建（name 与 problems[] 必填、version 默认 1.0、frozen 默认 false）与编辑（PATCH 可选字段）；SHALL 支持对 Suite 启动 run（api_key/dataset_path/model/strategies/budget_cap_usd，保留已有个人数据集选择）并以返回的真实 run_id 与 task_id 导航和观察进度至终态。后端不存在 Suite 删除端点，前端 SHALL NOT 提供删除入口。

#### Scenario: 创建 Suite 并出现在列表

- **WHEN** 用户以合法字段创建 Suite
- **THEN** 新 Suite 出现在列表且创建面板关闭

#### Scenario: 启动 run 后进度可见

- **WHEN** 用户对 Suite 启动 run
- **THEN** 界面保存选中的真实运行标识到 URL，以关联 task_id 观察进度，展示该运行的准确率/成本或错误，刷新可恢复

### Requirement: 学习曲线展示

详情页 SHALL 经 learning-curve 端点按模型分组绘制历史 run 的准确率与成本折线，并展示 trends 增长率（不足两条记录时按无趋势呈现）。历史数据来自该端点，前端 SHALL NOT 伪造 run 列表；曲线点 SHALL 可通过后端返回的 run_id 定位对应运行，并提供键盘可访问的等价导航。

#### Scenario: 多模型学习曲线渲染

- **WHEN** Suite 存在多个模型的已完成 run
- **THEN** 折线图按模型分组渲染准确率与成本序列，trends 增长率随之展示

#### Scenario: 选择历史曲线运行

- **WHEN** 用户选择某个曲线点或其等价运行链接
- **THEN** 页面加载该点实际 run_id 的详情，不使用当前历史页第一条或最新完成记录替代

## ADDED Requirements

### Requirement: 真实历史分页与显式运行恢复

前端 SHALL 接入当前所有者的套件历史，提供后端分页、状态筛选、运行选择和真实空态。选中运行 SHALL 保存在可刷新和分享的 URL 中，明确选择的运行 SHALL 独立于当前列表页查询，错误或无权访问 SHALL 明确反馈。运行与任务标识 SHALL 校验当前套件和关联实体，不猜测或替换。

#### Scenario: 默认页外的显式运行

- **WHEN** URL 指向不在当前历史页或当前状态筛选中的合法运行
- **THEN** 页面仍能展示该运行详情和关联进度，筛选或分页不会静默丢弃选择

#### Scenario: 无效或其他套件的链接

- **WHEN** URL 运行不存在、无权访问或不属于当前套件
- **THEN** 页面明确反馈且不展示其他运行作为替代

#### Scenario: 多个活动运行

- **WHEN** 重新进入页面发现多个 pending/running/paused 运行
- **THEN** 页面提供真实活动运行选择和更多记录导航，不将最新 completed 记录作为当前活动运行

### Requirement: 进度观察隔离和终态对账

前端 SHALL 区分 pending/running/paused 与 completed/failed/cancelled；终态停止无效轮询并刷新选中详情、历史和曲线，暂停保留进度且可手动重新核对。观察失败 SHALL 提供重试，账号、路由或运行变化 SHALL 清理旧请求和观察器，旧响应 SHALL NOT 污染当前页面。

#### Scenario: 终态刷新后停止

- **WHEN** 选中运行关联任务进入终态
- **THEN** 页面刷新真实运行结果、历史与曲线，并停止该任务自动轮询，不产生资源刷新循环

#### Scenario: 暂停和账号切换

- **WHEN** 已暂停运行被选中或用户切换账号
- **THEN** 暂停显示真实进度和手动刷新；账号切换清除旧账号运行内容，旧请求即使返回也不展示

#### Scenario: 双语窄屏与键盘操作

- **WHEN** 用户以中文或英文在 320px 窄屏或键盘模式操作历史与曲线
- **THEN** 运行选择、分页、刷新与错误反馈均可用，页面无整体横向溢出

```
