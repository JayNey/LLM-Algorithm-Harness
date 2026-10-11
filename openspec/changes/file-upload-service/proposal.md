## Why

Issue #153 需要可供前端调用的文件上传、题库合并、配置验证与结果下载服务。#152 已提供身份与权限基础，现有 CLI 导入器和报告模块可复用。

## What Changes

- 用户隔离的本地存储、UUID 文件名、元数据、上传限额与限流。
- JSON/CSV 题库验证和 `problem_id` 去重，追加与覆盖采用事务。
- JSON/YAML 配置验证、脱敏存储、配置模板库。
- 可查询的导入作业进度与错误报告。
- 所有者限定的文件、题库、结果 JSON/CSV/Markdown/HTML/PNG/ZIP 下载。
- 定时过期清理、任务删除时关联文件清理，以及 #149 worker 的发布结果入口。

## Capabilities

### New Capabilities
- `api/file-processing`: 文件上传、验证、批量导入、导出与生命周期。

### Modified Capabilities
无。

## Impact

影响 `api/`、上传依赖、测试和文档。#151 未合并时复用认证数据库连接，新增独立 `api_file_*` 表；不实现对象存储和队列基础设施。
