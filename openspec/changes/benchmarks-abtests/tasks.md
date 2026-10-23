# Tasks: benchmarks-abtests

## 1. 基准 Suite 簇

- [ ] 1.1 `benchmarks/types.ts` + `client.ts`（严格解析：suites 列表无分页壳/创建/详情/PATCH/run 202+task_id/run 详情标量/learning-curve）+ `session.tsx` + `presentation.ts`；单测 client.test
- [ ] 1.2 `TrendLine` 折线图加入 CompareCharts（按模型分组准确率/成本，trends 文字）
- [ ] 1.3 `BenchmarksPage`（内联创建面板 + 套件列表 + 编辑入口）与 `BenchmarkDetailPage`（信息/编辑 PATCH/启动 run 表单/run 进度 task_id 锚定/学习曲线 Tab）

## 2. AB 测试簇

- [ ] 2.1 `abtests/types.ts` + `validation.ts`（双变体必填、max_workers 1–20、seed ≥0、单模型单策略）+ `client.ts`（list/get/create/remove/run/results 子集严格解析）+ `session.tsx` + `runCreation.ts` + `presentation.ts`；单测 client/validation
- [ ] 2.2 `ABTestsPage`（useList 分页 + 状态筛选 + 删除）、`CreateABTestPage`（动态双变体表单）、`ABTestDetailPage`（5s 状态轮询至终态 + 完成后统计表：sample/formal baseline·treatment·ci95、检验三态 p 值、Welch t、失败分类）

## 3. 路由、验证与收尾

- [ ] 3.1 routes.tsx 增量（/benchmarks 换真实页、/benchmarks/:suiteId、/ab-tests、/ab-tests/new、/ab-tests/:testId）+ AppLayout 增挂两 Provider + package.json glob
- [ ] 3.2 `scripts/verify-benchmarks.mjs`（suite 列表/创建/学习曲线、ab 列表/详情场景）+ QA.md 说明
- [ ] 3.3 全量前端测试/tsc/eslint/prettier 绿；在 #166 记录第②步验收并提交关联 PR
- [ ] 3.4 独立审查两轮制 + 最后 commit 后三件套重验
