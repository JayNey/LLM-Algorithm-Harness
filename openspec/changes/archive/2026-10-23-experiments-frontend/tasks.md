# Tasks: experiments-frontend

## 1. 数据层

- [x] 1.1 `types.ts` + `validation.ts`：ExperimentJob/Config/ModelSpec/StrategyConfig/Budget/TaskSnapshot/Comparison(子集)/Panel/Pareto/OptimizeAdvisory 类型；创建草稿校验（models/strategies≥1、预算三型互斥至多一、max_workers 1–16、温度/token 范围）与列表 URL query 白名单回填
- [x] 1.2 `client.ts`：严格解析 createExperimentClient（list/get/create/remove/run/results/comparison/panel + task/cancelTask/runningExperimentTasks + pareto/optimize），含 204/202 与 task_id/progress 形状；session.tsx marker 键控 Provider
- [x] 1.3 `runCreation.ts` 创建→启动相位机（operation 计数、owner 守卫）；`useTaskProgress` 3s 轮询至终态（paused 停、失败 3 次暂停重试）
- [x] 1.4 数据层单测（client/validation/runCreation）转绿；package.json test glob 追加 `src/experiments`

## 2. 页面与图表

- [x] 2.1 `presentation.ts` + `ExperimentsPage`：服务端分页列表、状态筛选（URL query）、删除确认、运行中取消（running 任务索引 → DELETE /tasks/{id}）
- [x] 2.2 `CreateExperimentPage`：多模型/多策略动态表单 + 预算三型 + serial|parallel + 校验错误展示；创建成功导航详情
- [x] 2.3 `ExperimentDetailPage` 概览：配置摘要 + useTaskProgress 进度条 + 启动/取消/删除按钮语义显隐
- [x] 2.4 图表薄封装（echarts-for-react）：`WinRateHeatmap`（热力图 + significant 格子 p 值标注）、`ScatterPlot`、`RadarChart`、`BarCompare`
- [x] 2.5 详情页分析 Tab（惰性加载）：对比报告（组合指标表 + 胜率矩阵 + 成本效益）、面板（雷达/散点/柱状直绘 panel 数据）、帕累托（frontier 高亮 + 预算建议）、成本建议（三目标切换 + 排名表）

## 3. 路由与验证

- [x] 3.1 `routes.tsx` 增量添加 `/experiments/new`、`/experiments/:experimentId`（detailPages）
- [x] 3.2 `scripts/verify-experiments.mjs`：create/list/detail 三场景（浏览器 fixture 层，route mock 按真实契约）+ QA.md 追加运行说明
- [x] 3.3 全量前端测试/tsc/eslint/prettier 绿；在 #166 记录验收（命令、退出码、截图/报告路径）并提交关联 PR

## 4. 审查与重验（团队惯例，build 内完成）

- [x] 4.1 独立审查（只读子代理，两轮制：全量 → 修复 → 定点复审）
- [x] 4.2 最后一个 commit 后重跑三件套（npm test / tsc -b / eslint+prettier）
