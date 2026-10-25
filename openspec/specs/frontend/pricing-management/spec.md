# frontend/pricing-management Specification

## Purpose
TBD - created by archiving change settings-frontend. Update Purpose after archive.

## Requirements

### Requirement: 定价管理

用户 SHALL 能查看三源合并的模型定价目录（内置/自定义文件/覆盖标注）、按模型查看版本历史，并以追加方式提交自定义定价（最新覆盖生效，无编辑删除）。表单校验 SHALL 与后端 schema 对齐（非负价格）。

#### Scenario: 目录与来源标注

- **WHEN** 用户打开定价页
- **THEN** 目录列出各模型价格并标注来源类型，覆盖项可辨识

#### Scenario: 追加自定义定价

- **WHEN** 用户为某模型提交新价格
- **THEN** 目录与该模型历史随之更新，追加式覆盖语义在界面说明
