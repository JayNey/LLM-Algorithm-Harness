# Design: problems-frontend

> 范围：#163 真实契约子集。范围对齐声明见 issue #163 留言（2026-10-24）。基线 d0f275c。
>
> 流程确认（2026-10-24）：约 10 文件超 tweak 提示阈值；与前两步（#166 实验簇/基准簇，均为自包含前端簇且用户两次确认继续 tweak）完全同构，无跨模块架构协调、无后端改动。按既定先例继续 tweak。

## 契约盘点（upstream/main d0f275c，侦察已逐行核对）

- **列表**：`GET /evaluation-options/problems?source=all|shared|personal&limit(1..100)&offset` → `PaginatedData[ProblemOption{problem_id,title,difficulty|null,source:shared|personal}]`（固定 problem_id 升序；个人覆盖共享同 ID；**刻意不下发 description/tags/test_cases/source_url**，测试有防泄漏断言）。`GET /evaluation-options` → strategies + sources[{id,label,problem_count}]。
- **导入**：`POST /problems/upload`（multipart：file + mode=append|overwrite + validate=true，同步直导，响应 `data={file_id,job_id,validation:{total,valid,invalid,errors:[{index,errors:[{field,type}]}] 上限200条,errors_truncated,file_id,duplicates,imported,dataset_total}}`——错误明细形状见 api/files/parsing.py `problem_error`；失败回删文件）；`POST /problems/import`（JSON：file_id + mode，202 → `{job_id,task_id,status:pending}`）；`GET /imports/{job_id}` → `{job_id,status,processed,total,percentage(浮点，真除法),result}`——**completed 的 result 是 validation 报告，failed 的是 {status_code,detail}**（store.fail_job）。上传前置 `POST /files/upload`（响应 `data={file:{id,filename,size,...},parsed}`）拿 file_id（异步通道）；限制：≤100MiB、**导入管道仅 .json/.csv**（create_job 白名单；YAML 只在解析层存在）、速率 10 次/窗口。
- **导出**：`GET /problems/export?format=json|csv`（仅个人题库，全量含测试用例）→ 文件流。
- **历史**：`GET /results/problems/{problem_id}?status&limit&offset` → `PaginatedData[{problem_id,strategy,status,iterations|null,tokens|null,execution_time|null,run_id}]`（仅本人）。
- **前端现状**：`/problems` 路由已注册指向 Mock；四簇模式齐备（严格解析/session/useList/表格样式）；antd Upload 可用；无 markdown/饼图依赖（本 change 不需要）。

## 关键决策

1. **独立簇不引后端改动**：`frontend/src/problems/` 自建 client（evaluation-options 契约的独立严格解析实现，不 import evaluations 簇——两簇演进节奏不同）；session/useList 复用（useList 跨簇已有先例）。
2. **导入双通道**：≤5MiB 走同步直导（一步到报告，`/problems/upload`）；>5MiB 走异步（先 `/files/upload` 再 `/problems/import`，轮询 `/imports/{job_id}` 3s 至终态 failed|completed|cancelled，展示 processed/total/percentage）。阈值仅是前端交互选择，两通道对后端都合法。文件选择 antd Upload `beforeUpload` 返回 false 阻自动上传；同步通道手动 FormData，异步通道先 multipart 上传再 JSON 触发。
3. **overwrite 二次确认**：mode=overwrite 整库替换，选择时弹确认文案说明后果；append 默认。
4. **评估历史抽屉**：antd Drawer + 行内按钮；前端聚合 `attempts = items.length`、`passed = status==='passed'` 计数、通过率；分页随抽屉滚动（limit 20 上下页）。status 集合按 results 契约白名单解析。
5. **导出**：直接 `window.open(exportUrl)` 由浏览器带 Cookie 下载（GET 同源）；不解析内容。
6. **列表与创建页的关系**：共用后端契约但互不依赖；本页不提供「用此题创建评估」跳转（创建页有自己的选择器与已选状态，跳过去无法预选——避免半吊子入口；如需可后续接 URL 参数协议）。
7. **验证**：client/validation 单测（node:test）；`scripts/verify-problems.mjs` 三场景（list 渲染与筛选、import 同步报告、history 抽屉），浏览器 fixture 层。

## 风险与回退

- 纯前端新簇 + 一处路由换实现；回退 = 还原 Mock 一行 + 删目录。
- 上传限制（100MiB/速率）由后端强制，前端超限提示靠响应错误如实展示。
- 与并行批次冲突面：routes.tsx 零改动（Problems 路由已存在）。
