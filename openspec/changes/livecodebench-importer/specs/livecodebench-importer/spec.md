## Purpose

导入固定版本的 LiveCodeBench 公开基准题，保留 public/hidden 边界并确保输入数据不会触发任意反序列化。

## ADDED Requirements

### Requirement: 固定版本和可复现筛选
系统 SHALL 记录 release 版本、日期/难度/数量过滤条件、题目 ID 列表和内容摘要。

#### Scenario: 同版本重复导入
- **WHEN** 使用相同 release、过滤条件和相同缓存文件重复导入
- **THEN** 题目 ID 列表和摘要一致

### Requirement: 支持安全缓存格式
系统 SHALL 支持本地 JSON/JSONL 和可信静态 JSON/JSONL URL，不得直接执行任意下载内容。

#### Scenario: 不安全序列化字段
- **WHEN** private 测试是 base64/zlib/pickle 格式
- **THEN** 导入器跳过该字段并记录人工补全/安全说明，不调用 pickle.loads

### Requirement: 映射测试用途和协议
系统 SHALL 将 public/private 测试分别映射为 public/hidden，并按 testtype 映射 function/stdin_stdout。

#### Scenario: 混合测试题
- **WHEN** 一题包含 stdin public 测试和 function hidden 测试
- **THEN** 两组测试保留各自用途和协议元数据

### Requirement: 过滤和失败可见
系统 SHALL 支持日期、难度、数量筛选；数据不可用或格式变化时明确失败，不静默使用其他版本。

#### Scenario: 版本不存在
- **WHEN** 用户请求不支持的 release 版本
- **THEN** 导入失败并提示支持的版本列表
