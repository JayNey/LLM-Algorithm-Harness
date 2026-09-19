# 题目导入指南

本文档介绍如何使用 LLM Algorithm Harness 的导入功能从不同来源导入算法题目。

## 概述

导入器系统提供了可扩展的架构，允许从多种来源导入题目数据集，并自动处理校验、去重、报告生成等流程。

## 基本用法

### 导入本地 JSON 文件

```bash
harness import --source local-json --input data/new_problems.json
```

这会：
1. 读取指定的 JSON 文件
2. 校验每个题目的格式
3. 检测与现有数据集的重复
4. 显示导入摘要
5. 询问确认
6. 写入到默认数据集路径（`data/problems.json`）

### 预览模式

在实际写入前查看导入结果：

```bash
harness import --source local-json --input data/new_problems.json --preview
```

预览模式会执行完整的导入流程（读取、校验、去重），但不会修改目标数据集。

### 指定输出路径

```bash
harness import --source local-json --input data/new_problems.json --output data/custom.json
```

### 处理重复题目

导入器使用 `(source_platform, source_problem_id)` 组合唯一识别题目。

**重要说明**：
- 只有包含有效 `source_problem_id` 的题目才会被去重检测
- 如果 `source_problem_id` 为 `null` 或缺失，该题目会被视为唯一题目并总是添加到数据集中
- 这避免了来自不同平台但恰好使用相同 `problem_id` 的题目被错误地识别为重复

**跳过重复（默认）：**
```bash
harness import --source local-json --input data/new_problems.json --update-strategy skip
```

**覆盖重复：**
```bash
harness import --source local-json --input data/new_problems.json --update-strategy overwrite
```

### 跳过确认提示

```bash
harness import --source local-json --input data/new_problems.json --force
```

适用于自动化脚本或 CI/CD 流程。

### 严格模式

任何失败都返回错误退出码：

```bash
harness import --source local-json --input data/new_problems.json --strict
```

## 支持的导入来源

### local-json

从本地 JSON 文件导入题目。文件格式应为标准的 Problem schema 数组。

**示例：**
```bash
harness import --source local-json --input data/leetcode_problems.json
```

### leetcode

从 LeetCode 公开题目 URL 或 slug 导入题面、难度、标签、约束和 Python 入口信息：

```bash
harness import --source leetcode --input https://leetcode.com/problems/two-sum/ --preview
harness import --source leetcode --input two-sum --force
```

适配器只使用公开 GraphQL 题目查询。受限题目、限流、网络超时和不支持的域名会返回明确失败；没有可靠公开期望输出的题目会保存为 `needs_manual_completion`，不会猜测测试答案或声称拥有隐藏测试。RSS/每日题目订阅适合做题目发现，正式导入仍需要通过 URL/slug 查询题面。

### mock

生成测试用的模拟数据，用于演示和测试。

**示例：**
```bash
# 生成 5 个模拟题目
harness import --source mock --input 5
```

### livecodebench

LiveCodeBench 导入需要一个固定版本的本地 JSON/JSONL 缓存：

```bash
harness import --source livecodebench \
  --input data/livecodebench-release-v6.json \
  --release-version release_v6 \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --difficulty hard \
  --import-limit 100 \
  --preview
```

导入报告会记录 release、过滤条件、源文件 SHA-256 和确定的题目 ID 列表。JSON/JSONL 中的 public/private 测试会分别映射为公开/隐藏测试；压缩或 pickle 私有字段不会被反序列化，会标记人工补全。使用前应根据 [LiveCodeBench 官方仓库](https://github.com/LiveCodeBench/LiveCodeBench) 的许可和可再分发范围准备本地缓存。

## 导入报告

每次导入完成后会显示详细报告：

```
Import Summary:
  Total problems in input: 10
  Successfully validated: 8
  Failed validation: 2
  Duplicates (skipped): 3
  Duplicates (overwritten): 0
  New problems to import: 5

Failed problems:
  - Index 3 (id: problem-004): Missing required field: title
  - Index 7 (id: problem-008): Invalid difficulty: super-hard

Import Report:
  Timestamp: 2026-09-18T10:30:00Z
  Successful: 8
  Failed: 2
  Duplicates skipped: 3
  Duplicates overwritten: 0
```

## 退出码

- `0` — 全部成功
- `1` — 部分成功（有失败项但至少有一个成功）
- `2` — 全部失败或严重错误
- `3` — 严格模式下任何失败

## 数据格式要求

导入的 JSON 文件应包含 Problem 对象数组。每个题目必须包含以下必需字段：

```json
[
  {
    "problem_id": "unique-id",
    "title": "Problem Title",
    "description": "Problem description (min 10 chars)",
    "difficulty": "easy|medium|hard",
    "source_platform": "platform-name",
    "source_problem_id": "platform-specific-id",
    "public_test_cases": [
      {
        "input": {"param": "value"},
        "expected_output": "expected_result"
      }
    ]
  }
]
```

**可选字段：**
- `tags` — 题目标签列表
- `constraints` — 约束条件
- `source_url` — 原始题目 URL
- `source_version` — 数据集版本
- `feedback_test_cases` — 反馈测试用例
- `hidden_test_cases` — 隐藏评测用例

## 去重机制

导入器通过 `(source_platform, source_problem_id)` 识别题目：

- 相同平台 + 相同题号 = 重复
- 不同平台的相同题号 = 不同题目（允许共存）

**示例：**
```json
// 这两个题目会被视为重复（相同平台和题号）
{"source_platform": "leetcode", "source_problem_id": "001", ...}
{"source_platform": "leetcode", "source_problem_id": "001", ...}

// 这两个题目不会被视为重复（不同平台）
{"source_platform": "leetcode", "source_problem_id": "001", ...}
{"source_platform": "codeforces", "source_problem_id": "001", ...}
```

## 错误处理

### 部分成功

如果批量导入中有部分题目失败，导入器会：
1. 成功导入所有有效题目
2. 在报告中列出失败项及原因
3. 返回退出码 1（非严格模式）或 3（严格模式）

### 常见错误

**文件不存在：**
```
Error: Input file not found: data/problems.json
```

**JSON 格式错误：**
```
Error: JSON file must contain an array of problems
```

**缺少必需字段：**
```
Problem at index 3 (id: test-004): Missing required field: description
```

**难度值无效：**
```
Problem at index 5 (id: test-006): Invalid difficulty: super-easy
```

## 创建自定义导入器

你可以为新的题库平台创建自定义导入器。

### 步骤

1. 在 `src/importers/` 创建新文件
2. 继承 `ProblemImporter` 基类
3. 实现所有抽象方法
4. 在 `src/main.py` 的 `IMPORTERS` 字典中注册

### 示例

```python
from src.importers.base import ProblemImporter
from src.models import Problem

class MyPlatformImporter(ProblemImporter):
    def fetch_problems(self, source: str):
        # 从你的平台拉取数据
        pass

    def transform_to_schema(self, raw_data):
        # 转换为 Problem 对象
        pass

    def detect_duplicates(self, problems, existing, strategy):
        # 去重逻辑（可以复用基类实现）
        pass

    def generate_report(self, result, source, output_path, preview):
        # 生成报告
        pass
```

**注册导入器：**

在 `src/main.py` 中：

```python
IMPORTERS = {
    "local-json": LocalJsonImporter,
    "mock": MockPlatformImporter,
    "my-platform": MyPlatformImporter,  # 新增
}
```

然后就可以使用：

```bash
harness import --source my-platform --input <source-identifier>
```

## 最佳实践

1. **先预览再导入**：使用 `--preview` 查看导入结果
2. **备份现有数据**：导入前备份 `data/problems.json`
3. **使用版本控制**：将数据集纳入 git 管理
4. **明确来源标识**：设置准确的 `source_platform` 和 `source_problem_id`
5. **保存导入报告**：导入后保留报告用于审计

## 故障排除

### 导入后题目数量不对

检查导入报告中的 "Duplicates skipped" 数量。如果需要覆盖，使用 `--update-strategy overwrite`。

### 某些题目导入失败

查看失败项详情，根据错误信息修复源数据后重新导入。

### 原子写入失败

检查：
- 目标路径是否有写权限
- 磁盘空间是否充足
- 文件是否被其他程序锁定
