# Proposal: problems-frontend（issue #163：题目管理页，真实契约范围）

## Why

#163 要求题目管理前端。现状 `/problems` 是 Mock 占位页。后端真实存在的题目面只有两块：#216 的只读元数据列表（为创建评估服务）与 #153 的个人题库导入/导出管道。本 change 在真实契约内交付题目管理页；范围已在 issue #163 留言（2026-10-24）与维护者对齐，后端不支持的子项不做假入口。

## What Changes

- 新增 `frontend/src/problems/` 功能簇（四簇既定模式）：`types.ts`、`client.ts`（严格解析：options/problems 复用 evaluations 契约 + `uploadProblems`（multipart 同步直导）/`startImport`（异步 202）/`importJob`（进度）/`exportUrl`（下载）/`problemHistory`（评估历史））、`session.tsx`、`validation.ts`（导入表单：文件必选、mode 白名单、格式白名单）、`presentation.ts`（难度/来源中文标签）。
- 新增 `pages/Problems/ProblemsPage.tsx` 替换 Mock 占位：服务端分页表格（problem_id/标题/难度/来源），来源筛选（all/shared/personal + 计数徽标）回 URL；行内「评估历史」按钮展开抽屉（`/results/problems/{id}` + 前端聚合次数/通过率）；「导出」按钮（json/csv 下载个人题库）。
- 新增导入面板（页内折叠区）：文件选择 + mode（append/overwrite 单选，overwrite 二次确认）+ 同步直导（小文件）或异步导入（大文件）双通道选择；同步通道展示完整 validation 报告（total/valid/invalid/duplicates/imported/dataset_total/errors 明细列表）；异步通道轮询 `GET /imports/{job_id}` 进度条至终态。
- `routes.tsx` 零改动（`/problems` 已注册，仅换页面实现）；`package.json` test glob 追加 `src/problems`。
- 单测（node:test）：client 严格解析各拒绝路径与 validation 报告形状、validation 导入表单校验、URL 白名单。
- 新增 `scripts/verify-problems.mjs`（list/import/history 场景，浏览器 fixture 层）+ QA.md 说明。

**明确不做（后端不支持，issue 留言已声明）**：关键词搜索、标签/难度筛选、排序、题目详情页、编辑/删除（单题与批量）、平台抓取导入、Markdown 渲染、相似推荐、难度/标签分布统计。**不新增后端端点**（共享题只读是既有安全策略）。

## Capabilities

### New Capabilities

- `frontend/problems-management`：真实契约内的题库浏览（元数据列表 + 来源筛选）、导入管道（同步/异步双通道 + 报告）、导出与单题评估历史。

### Modified Capabilities

- 无：复用 evaluations 的 evaluation-options 契约（零改后端、零改 evaluations 簇代码——client 侧独立实现同契约的严格解析）。

## Impact

- 新文件约 8 个，修改 2 个（pages/Problems 换实现、package.json glob）。
- 不新增 npm 依赖；文件上传用 antd Upload 的受控 beforeUpload（false 阻止自动上传，手动 FormData 提交）。
- 与真实评估批次零共享文件冲突（新目录 + 既有路由换实现）。
