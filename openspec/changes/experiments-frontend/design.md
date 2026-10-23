# Design: experiments-frontend

> 范围：#166 第①步实验管理簇（基准 Suite + AB 测试为第②步后续 change）。范围对齐声明见 issue #166 留言（2026-10-22）。

## 契约盘点（upstream/main 47a9a5a，已逐行核对）

- **实验**（api/routes/experiments.py + services/experiment_service.py）：`_job_view = {id, name, status, config, error_message, created_at, updated_at}`；`config` 为创建请求的 JSON（`name/dataset_path/models[]/strategies[]/repeats/budget/execution/max_workers/problem_filters/api_key_id`）；`ModelSpec{model,base_url?,temperature?,api_key_id?}`、`StrategyConfig{name,max_iterations?,temperature?,max_tokens?,system_prompt?,custom_params?}`、`ProblemBudget{max_calls?,max_tokens?,max_seconds?}`；端点 POST /experiments(201)、GET /experiments?status&limit&offset、GET/DELETE /{id}(200/204)、POST /{id}/run(202+task_id)、GET /{id}/results|comparison|panel(仅 completed)。运行中不可删除（service 层拒绝）。
- **任务**（api/routes/tasks.py）：`AsyncTaskResponse{id,task_type,entity_id,celery_task_id,status,progress{current,total,percentage,current_step}|null,error_message,created_at,started_at,completed_at,updated_at}`；GET /tasks/{id}、DELETE /tasks/{id}（取消）、GET /tasks?status&task_type&limit&offset（无 entity_id 过滤）。**实验/基准无 WS**（ws.py 仅 evaluation）→ 进度只能轮询。
- **分析**：`GET /{id}/comparison`（全量报告：combinations[]、model_comparison.strategies{matrix[{model,solved,against{wins,ties,losses,win_rate}}],significance[{a,b,p_value,significant,…}]}、cost_effectiveness[]、pareto…）；`GET /{id}/panel`（radar/scatter/bar/matrix_tables/algorithm_radar，中文单元格已拼好）；`POST /pareto/analyze`（无状态：comparisons[]+budgets+accuracy_metric）；`POST /optimize`（无状态：comparison+budget+min_accuracy+objective）。
- **前端现状**：/experiments 路由已注册指向 mock；evaluations 簇模式可同构复制；echarts + echarts-for-react 已在依赖；`components/charts|forms` 目录为空；测试 glob 写死在 package.json；CI 无前端 job，门禁为 husky lint-staged + 本地验证。

## 关键决策

1. **同构新簇**：`frontend/src/experiments/` 按 evaluations 模式建 types/validation/client/session/presentation；严格解析白名单只解析 UI 需要的字段（config 内仅取模型/策略数量与关键配置摘要），任何形状不符抛 `ApiClientError('实验接口响应格式不兼容')`；client 注入 `useAuthStore.httpClient()`（Cookie/CSRF/共享刷新）。`getTask/cancelTask/runningTaskIndex` 放本簇 client（跨簇复用留待第②步按需上提）。
2. **进度轮询**：`useTaskProgress(taskId, enabled)`——3s 间隔轮询 `GET /tasks/{id}`，进入 `completed|failed|cancelled` 终态即停（`paused` 停轮询、恢复由用户动作触发）；组件卸载/换 id 即 AbortController 取消；轮询失败连续 3 次暂停并展示重试（避免无退避打点）。**不用 WebSocket**（后端不支持）。
3. **创建→启动**：`runCreation.ts` 仿 evaluations creation.ts——`editing/creating/created/starting/queued/start-error` 相位 + operation 计数防竞态 + owner 失配拒写；创建成功即导航详情页，详情页提供「启动」；创建表单校验（validation.ts）：models≥1、strategies≥1、budget 三型至多填其一、max_workers 1–16、temperature/max_tokens 范围对齐后端 schema。
4. **列表页**：antd Table 服务端分页（limit 钳 1–100 默认 20）+ 状态筛选（pending/running/paused/completed/failed/cancelled 白名单，写入 URL query 可回填）+ 删除（确认；运行中后端拒绝则原样展示错误）；**运行中取消**：行内按钮 → 先查 `GET /tasks?task_type=experiment&status=running&limit=100` 建 entity_id→task 映射（每次点击现查，避免常驻轮询）→ `DELETE /tasks/{task_id}`。**不做内联搜索**（后端无关键词参数，issue 假设不成立）。
5. **详情页**：概览（配置摘要 + 进度条 + 启动/取消/删除按钮，按 status/can 语义显隐）；其余为 Tab——**对比报告**（组合指标表 + 胜率矩阵 ECharts heatmap，significant 格子标注 p 值 + 成本效益表）；**面板**（panel 端点数据直绘：雷达/散点/柱状）；**帕累托**（comparison 作为单元素输入 `POST /pareto/analyze`，散点 + frontier 高亮 + 预算建议表）；**成本建议**（comparison → `POST /optimize`，三目标切换 + 排名表 + 预算分层）。analysis 类 Tab 惰性加载（进入才请求）。
6. **图表组件**：`components/charts/` 下新增 `WinRateHeatmap.tsx`、`ScatterPlot.tsx`、`RadarChart.tsx`、`BarCompare.tsx`（echarts-for-react 薄封装，props 传数据，无业务逻辑），供实验簇与第②步复用。
7. **验证脚本**：`scripts/verify-experiments.mjs` 照 verify-evaluations.mjs 骨架（playwright 外部加载、route mock、report 结构），本期实现 create/list/detail 三场景；不进 CI，运行方式写入 docs/frontend/QA.md 追加段。
8. **测试**：client.test.ts（严格解析：正常/缺字段/类型错/204/202/task_id/progress 形状）、validation.test.ts（草稿校验与 URL query 回填）、runCreation.test.ts（相位机 + 竞态 + owner 失配）、presentation.test.ts（标签映射）；package.json test glob 追加 `src/experiments`。

## 风险与回退

- **并行冲突**：真实评估批次在改 routes.tsx/共享组件——本 change 只追加 experiments 条目与新簇目录；如上游 detailPages 先变，追加式合并即可。
- **契约再漂移**：experiments 路由自 #156 合入后稳定（近期仅 monitoring/auth 在动）；严格解析会在任何形状漂移时显式失败而非静默错绘。
- **回退**：删新簇目录 + 还原 routes.tsx/package.json 两处增量；无后端改动、无数据迁移。
- **规模**：约 15 文件，超 tweak 阈值已由用户确认继续 tweak（2026-10-22）；无跨模块架构协调，架构参照 evaluations 既定模式。
