# Tasks: problems-frontend

## 1. 数据层

- [x] 1.1 `problems/types.ts` + `client.ts`：严格解析（options/problems 复用契约、uploadProblems multipart 同步、startImport/importJob 异步、problemHistory、exportUrl 构造）+ `session.tsx`；单测 client.test（各拒绝路径、validation 报告形状、导入作业形状）
- [x] 1.2 `validation.ts`（URL 来源白名单回填）+ `presentation.ts`（难度/来源/导入状态中文标签）；文件/mode 校验内联于 client.ts（validateImportFile），测试归并在 client.test（复审修正记录）

## 2. 页面

- [x] 2.1 `ProblemsPage`：分页表格（problem_id/标题/难度/来源）、来源筛选回 URL + 计数徽标、导出按钮（json/csv）
- [x] 2.2 导入面板（折叠区）：文件选择（beforeUpload 阻自动）、mode 单选（overwrite 确认）、同步/异步双通道、validation 报告展示（含 errors 明细与截断提示）、异步进度轮询
- [x] 2.3 评估历史 Drawer：`/results/problems/{id}` + 前端聚合（次数/通过数/通过率）+ 分页

## 3. 验证与收尾

- [x] 3.1 package.json glob 追加 `src/problems`；`scripts/verify-problems.mjs`（list/import/history 场景）+ QA.md 说明
- [ ] 3.2 全量测试/tsc/eslint/prettier 绿；#163 记录验收并提交关联 PR
- [ ] 3.3 独立审查两轮制 + 最后 commit 后三件套重验
