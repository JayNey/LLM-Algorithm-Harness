## Context

`ProblemsPage` 的导入提示与 `validateImportFile` 的扩展名白名单均为 JSON/CSV。同步 `/problems/upload` 和异步 `/problems/import` 都经由 `FileStore.create_job` 检查同一组扩展名。

## Decisions

- 在个人题库增量规格中明确现有格式范围，归档时同步主规格。
- 在前端 QA 指南记录支持格式、同步与异步分流及 YAML 拒绝预期。通过现有文件服务测试和格式抽查核对运行时契约。
- YAML 配置和通用文件上传属于文件服务指南中单独描述的用途。
