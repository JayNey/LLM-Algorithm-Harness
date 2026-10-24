# frontend/problems-management Specification

## Purpose
TBD - created by archiving change problems-frontend. Update Purpose after archive.

## Requirements

### Requirement: 题库元数据浏览

前端 SHALL 提供题目列表页：服务端分页（limit 1–100）与来源筛选（all/shared/personal，筛选状态可经 URL 恢复），展示 problem_id、标题、难度与来源；来源选项 SHALL 附带题库计数。列表端点只下发元数据，前端 SHALL NOT 展示或伪造题目描述、测试用例或来源链接；SHALL NOT 提供关键词搜索、标签/难度筛选与排序入口（后端无此参数）。

#### Scenario: 来源筛选经 URL 恢复

- **WHEN** 用户以 personal 筛选访问列表并把 URL 分享或在刷新后打开
- **THEN** 列表按 personal 过滤且筛选器状态与 URL 一致

#### Scenario: 元数据之外的字段不出现

- **WHEN** 列表渲染任意题目行
- **THEN** 行内只有 problem_id、标题、难度、来源，无描述/测试用例/来源链接占位

### Requirement: 个人题库导入

前端 SHALL 提供文件导入（JSON/CSV/YAML）：小文件走同步直导并展示完整 validation 报告（总数/有效/无效/重复/导入数/库存量与错误明细，错误列表截断时如实提示）；大文件走异步导入（上传 → 触发 → 轮询作业进度至终态）。overwrite 模式 SHALL 要求二次确认并说明整库替换后果。后端拒绝（格式/大小/速率）SHALL 如实展示错误。

#### Scenario: 同步导入报告呈现

- **WHEN** 用户导入一个含重复与无效条目的小文件
- **THEN** 报告展示 total/valid/invalid/duplicates/imported 与错误明细列表，截断时提示条数上限

#### Scenario: overwrite 需确认

- **WHEN** 用户选择 overwrite 模式并提交
- **THEN** 先弹出整库替换后果确认，确认后才发起请求

### Requirement: 题库导出与评估历史

前端 SHALL 提供个人题库导出入口（json/csv 下载）；SHALL 为题目行提供评估历史视图：读取该题执行历史并在前端聚合评估次数与通过率，仅展示本人数据。

#### Scenario: 导出下载

- **WHEN** 用户点击导出并选择格式
- **THEN** 浏览器发起带凭据的下载请求

#### Scenario: 历史聚合

- **WHEN** 用户打开某题的评估历史
- **THEN** 展示该题历次执行记录与聚合的次数/通过率，无记录时如实提示
