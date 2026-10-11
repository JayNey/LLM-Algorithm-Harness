## ADDED Requirements

### Requirement: 受限私有上传
系统 SHALL 在解析前校验身份与上传限额，并验证文件大小、扩展名和实际内容，使用唯一物理文件名记录所有者、时间和大小。

#### Scenario: 分块请求超限
- **WHEN** 上传在分块读取过程中超过配置限额
- **THEN** 返回 413，关闭临时句柄且不保留上传文件

#### Scenario: 伪装二进制
- **WHEN** 可执行文件使用 JSON/YAML/CSV 扩展名上传
- **THEN** 拒绝内容，不执行或公开该文件

### Requirement: 题库验证和导入
系统 SHALL 验证 Problem Schema，报告成功/失败及重复数，按 problem_id 在事务中执行追加或覆盖，并支持查询导入进度。

#### Scenario: 并发追加
- **WHEN** 同一用户并发追加不同题目
- **THEN** 所有有效新增记录保留，不因读取旧快照发生丢失

### Requirement: 安全配置
系统 SHALL 验证 HarnessConfig/ExperimentConfig 并保存脱敏配置，提供可查询模板。

#### Scenario: 上传含密钥的 YAML
- **WHEN** 用户上传包含真实 API 密钥的有效配置
- **THEN** 规范化存储、响应和下载不包含密钥明文

### Requirement: 所有者下载
系统 SHALL 仅允许资源所有者下载文件、题库、结果和图表，支持 JSON/CSV/Markdown/HTML/PNG/ZIP，拒绝访问任意本机路径。

#### Scenario: 非所有者下载
- **WHEN** 用户 B 请求用户 A 的结果或文件
- **THEN** 返回 404，不读取或打包 A 的内容

### Requirement: 文件生命周期
系统 SHALL 定时清理过期上传和派生文件，在任务删除后清理关联文件，并阻止迟到 worker 重建已删除任务的文件。

#### Scenario: 删除后的迟到结果
- **WHEN** 用户删除任务后 worker 尝试发布结果
- **THEN** 拒绝发布，下载仍返回 404
