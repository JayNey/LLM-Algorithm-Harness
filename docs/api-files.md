# 文件上传、批量导入与下载（#153）

## 启动与存储

先完成 [API 认证配置](api-authentication.md)，安装 `pip install -e '.[dev]'`，再启动 API。全部文件接口使用 `Authorization: Bearer <access_token>`。

本版本使用用户隔离的本地目录和认证 SQLite 中的独立 `api_file_*` 表：

```text
uploads/users/<user-id>/
  temp/       原始上传与处理暂存
  configs/    已验证、脱敏的配置
  results/    可信 worker 发布的结果
```

物理文件名使用 UUID，原始文件名仅作显示和附件名称。上传目录默认被 Git 忽略；自定义目录也应排除在版本控制之外。元数据记录所有者、文件 ID、名称、大小、SHA256、时间、分类和任务 ID；API 不暴露本机路径。

环境变量或 `.env` 可设置：

- `UPLOAD_DIR`：默认 `uploads`。
- `FILE_UPLOAD_MAX_BYTES`：默认 104857600（100 MiB）。
- `FILE_CONFIG_MAX_BYTES`：默认 1048576（1 MiB）。
- `FILE_MAX_USER_BYTES`：默认 536870912（512 MiB），限制每用户已保存文件总量；删除失败的文件仍计入。
- `FILE_TTL_SECONDS`：默认 86400（原始上传保存 24 小时）。
- `FILE_CLEANUP_INTERVAL_SECONDS`：默认 300。
- `FILE_UPLOAD_RATE_LIMIT`：默认每用户和每客户端 IP 每认证窗口各 10 次上传。
- `FILE_MAX_CONCURRENT_TRANSFERS`：默认每进程 2 项上传/下载。
- `FILE_UPLOAD_TIMEOUT_SECONDS` / `FILE_UPLOAD_IDLE_SECONDS`：默认 120 / 15 秒，限制接收上传的总时间和两次数据之间的空闲时间。
- `FILE_IMPORT_MAX_ITEMS`：默认 10000，限制题库及发布结果条数。
- `FILE_MAX_CONCURRENT_IMPORTS`：默认每进程 2 项处理。
- `FILE_MAX_ACTIVE_IMPORTS`：默认共享数据库最多 8 项等待/处理中的导入。
- `FILE_IMPORT_TIMEOUT_SECONDS`：默认 3600，超过无进度期限的作业被标记失败。

目录与数据库必须成对迁移；不同实例共用认证数据库时应共用文件目录。用户题库合并、作业状态和文件限额采用 SQLite 事务。#151 已将评估任务接入独立业务数据库；文件元数据、私有题库与导入作业仍使用上述认证 SQLite 中的 `api_file_*` 表，尚未迁移至业务库或对象存储。

## 上传

使用 multipart 表单，字段 `file` 必须恰好一个。额外字段最多 5 个，单字段最多 64 KiB；总请求不得超过文件限额加 64 KiB 包装开销。服务在 multipart 解析前认证、限流和限制并发，接收时统计真实字节。超限返回 413，空闲/接收超时返回 408；临时磁盘句柄会关闭。

支持 `.json/.yaml/.yml/.csv`、UTF-8 或 UTF-8 BOM。除扩展名和 MIME 白名单外，还验证文本语法；二进制头、可执行内容、重复对象键、YAML 标签/别名、过深结构和非有限数字被拒绝。结构上限为 64 层、500000 个节点；CSV 需英文唯一字段名，最多 128 列，首行最多 64 KiB。上传内容不会执行。

### 通用上传

`POST /api/v1/files/upload` 返回 `data.file` 元数据。JSON/YAML 中明显属于评估配置的对象必须走配置端点，以避免把配置密钥原样保存。

```bash
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'file=@problems.json'
```

`GET /api/v1/files/{file_id}` 查询自己的元数据；`GET /api/v1/files/{file_id}/download` 下载；`DELETE /api/v1/files/{file_id}` 删除。其他用户请求返回 404；正在导入的文件不能删除。已导入题库保存在数据库中，删除原始上传不会删除题库。

### 题库上传

`POST /api/v1/problems/upload` 支持 JSON 数组或 CSV，表单 `mode=append`（默认）或 `mode=overwrite`。

```bash
curl -X POST http://localhost:8000/api/v1/problems/upload \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'file=@problems.json' -F 'mode=append' -F 'validate=true'
```

成功响应 `data` 包含 `file_id/job_id/validation`。验证报告包含 `total/valid/invalid/duplicates/imported/dataset_total/errors/errors_truncated`；无效记录只返回索引及字段/类型诊断，不返回整条内容。最多返回 200 条错误，计数仍覆盖全部记录。

- 强制 `Problem` Schema 与完整性验证，未知顶层字段会报错；`validate=false` 不能绕过验证。
- 部分成功时只导入有效条目；空题库或全部无效返回 400，不修改现有题库。
- 追加保留原记录，按 `problem_id` 去重；同次请求的重复 ID 取第一条。
- 覆盖用本次有效记录替换当前题库；并发追加使用事务读取最新状态，不丢失另一请求的数据。
- JSON 支持旧 `test_cases` 与现有分阶段用例字段，复用 LocalJsonImporter 转换有效条目。
- 普通 CSV 使用 `Problem` 字段名。`tags/test_cases/public_test_cases/feedback_test_cases/hidden_test_cases/judge_config/source_metadata/manual_completion_notes` 单元格采用 JSON；其他字段为普通文本。

### 后台导入与进度

先通用上传 JSON/CSV，再 `POST /api/v1/problems/import`：

```json
{"file_id":"id-returned-by-upload","mode":"append"}
```

返回 202 与 `data.job_id`。通过 `GET /api/v1/imports/{job_id}` 查看 `status/processed/total/percentage/result`，每 100 条记录更新进度。提交请求为小 JSON，最多 16 KiB。

作业状态为 `pending/running/completed/failed`。来源文件已有活跃导入时返回 409；共享作业容量或传输容量不足时返回 429 和 `Retry-After`。进度只对作业所有者可见。

当前后台处理为进程内 BackgroundTasks，尚未接入 #149 的队列；进程崩溃后不会伪记成功，过期作业在清理时变为失败，用户可重新提交。题库提交和最终作业完成状态在同一事务中。

### 配置上传和模板

- `POST /api/v1/configs/upload`：文件 JSON/YAML/YML，表单 `config_type=harness`（默认）或 `experiment`。
- 使用现有 HarnessConfig / ExperimentConfig 验证，失败返回字段和错误类型。
- 只保存规范化、脱敏的配置；响应及下载不包含输入 API 密钥明文。处理暂存立即删除，文件后缀保留原格式。
- `GET /api/v1/configs/templates`：模板列表；`GET /api/v1/configs/templates/vanilla` 与 `/experiment`：模板内容。
- 模板和已保存配置的 API 密钥为 `[REDACTED]`。执行时必须由 worker 绑定 #152 中当前用户的密钥、已授权的数据集和输出目录；不能直接将上传配置中的路径、URL 或环境引用传给 CLI。
- 不提供可选的配置版本管理与 MinIO/S3 存储。

## 下载与导出

- `GET /api/v1/problems/export?format=json|csv`：导出当前用户题库。
- `GET /api/v1/results/{run_id}/download?format=...` 或 `/export?format=...`：JSON、CSV、`md/markdown`、HTML、PNG、ZIP。
- `GET /api/v1/results/{run_id}/charts/success-rate`：成功率 PNG。

导出的题库 CSV 包含全部 `Problem` 字段，并带 `_harness_csv_encoding=json-v1`。每个单元格为 JSON 值，用于保留可空值、判题配置、入口、来源信息和公式样式字符串，重新上传能准确往返；这种字符串单元格在表格程序中以引号开头，避免作为公式执行。普通外部 CSV 无此标记时仍按上一节的普通字段方式导入。

结果 CSV 复用 CSVExporter，并转义公式开头。Markdown/HTML 是完整规范化结果的安全文本报告；HTML 转义上传/生成内容，Markdown 阻止代码块逃逸。PNG 复用 ChartGenerator；ZIP 仅包含固定的 `results.json/results.csv/report.md/report.html/success-rate.png` 名称，不接受用户路径。

全部下载采用附件、`nosniff`、`no-store` 和限制性 CSP。错误所有者与不存在资源统一 404。结果必须由可信 worker 发布到已经登记且未删除的任务；未产生真实结果时返回 404，不开放全局 CLI 结果目录。

## #149 worker 接入与删除

评估创建时自动登记 `run_id` 与可信 `user_id`。worker 使用任务中可信的 ID 调用：

```python
app.state.files.publish_results(run_id, user_id, results_by_strategy)
```

`results_by_strategy` 是策略名到 `ExecutionResult` 列表的映射，发布前会规范化并脱敏。HTTP 不提供指定所有者或本机路径的结果发布接口。当前 #148 执行器仍是模拟器，需要 #149 接入此发布函数后才能下载实际运行结果。

删除评估任务先写入文件归属删除标记，再清理关联文件；迟到 worker 不能重新发布。删除遇到 Windows 占用等错误时隐藏文件并保留元数据，由下次清理重试。原始上传按期限删除，当前题库保留；派生下载在内存中生成，CSV 暂存立即清理，不永久积累派生文件。

崩溃留下的 `.part` 暂存与改名后未登记的 UUID 文件，在至少一小时且不短于原始上传期限的保守窗口后回收。已登记、活跃导入引用、非服务生成名称和 symlink 路径不作为孤立文件删除。

## 验证

```bash
python -m pytest tests/test_api_files.py tests/test_api_auth.py --no-cov -q
python -m pytest -m 'not online' --cov --cov-report=term
```

Multipart 行为依据 [FastAPI 文件上传接口](https://fastapi.tiangolo.com/tutorial/request-files/)；测试另使用真正分块的 ASGI 输入，验证文件落盘后超限、断开和空闲超时均会关闭句柄。
