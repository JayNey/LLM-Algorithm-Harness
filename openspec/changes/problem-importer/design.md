# Design: 可扩展题库导入器

## 架构概述

本设计引入导入器接口（`ProblemImporter`），将题库导入标准化为可插拔的适配器架构。每个平台（本地 JSON、LeetCode、LiveCodeBench 等）实现自己的适配器，复用统一的校验、去重和持久化逻辑。

## 核心组件

### 1. ProblemImporter 抽象基类

位置：`src/importers/base.py`

抽象方法：
- `fetch_problems()` — 拉取或读取原始题目数据，返回原始格式
- `transform_to_schema(raw_data)` — 转换为 `Problem` 对象列表
- `detect_duplicates(problems, existing)` — 检测重复（基于 `source_platform` + `source_problem_id`）
- `generate_report(results)` — 生成导入报告字典

基类提供的通用方法：
- `validate_problems(problems)` — 调用 `validators.validate_problem_schema` 校验每个题目
- `persist_dataset(problems, path)` — 原子写入（临时文件 + 重命名）

### 2. LocalJsonImporter

位置：`src/importers/local_json.py`

功能：从本地 JSON 文件导入题目，替代 `ProblemLoader` 的直接加载逻辑。

实现：
- `fetch_problems()` — 读取 JSON 文件
- `transform_to_schema()` — 解析 JSON 数据为 `Problem` 对象
- 复用基类的校验和持久化方法

### 3. CLI Import 命令

位置：`src/main.py` 新增子命令

参数：
- `--source` (必需) — 导入器类型
- `--input` (必需) — 输入路径
- `--output` (可选，默认 `data/problems.json`)
- `--preview` — 预览模式标志
- `--update-strategy` (可选，默认 `skip`) — `skip` 或 `overwrite`
- `--force` — 跳过确认

流程：
1. 根据 `--source` 实例化对应的导入器
2. 加载现有数据集（如果存在）
3. 调用导入器的 `fetch_problems()` 和 `transform_to_schema()`
4. 调用 `validate_problems()` 校验
5. 调用 `detect_duplicates()` 检测重复
6. 显示导入摘要
7. 如果非预览模式且用户确认（或 `--force`），调用 `persist_dataset()` 写入
8. 显示导入报告

### 4. 导入报告格式

```json
{
  "timestamp": "2026-09-18T10:30:00Z",
  "source": "local-json",
  "input_path": "data/new_problems.json",
  "output_path": "data/problems.json",
  "preview_mode": false,
  "update_strategy": "skip",
  "summary": {
    "total_attempted": 10,
    "successful": 8,
    "failed": 2,
    "duplicates_skipped": 3,
    "duplicates_overwritten": 0
  },
  "successful_problems": ["problem-1", "problem-2", ...],
  "failed_problems": [
    {
      "index": 3,
      "problem_id": "unknown",
      "error": "Missing required field: title"
    }
  ],
  "duplicates": [
    {
      "problem_id": "leetcode-001",
      "action": "skipped"
    }
  ]
}
```

## 数据模型变更

`src/models.py` 中的 `Problem` 模型可选地支持以下元数据字段（通过 Pydantic `Field` 的 `default` 参数）：
- `imported_at: Optional[str]` — 导入时间戳（ISO 8601）
- `source_version: Optional[str]` — 源版本信息
- `import_warnings: Optional[List[str]]` — 导入警告列表

这些字段不是必需的，以保持向后兼容。

## 去重逻辑

去重键：`(source_platform, source_problem_id)`

现有题目映射：
```python
existing_map = {
    (p.source_platform, p.source_problem_id): p
    for p in existing_problems
}
```

对于每个新题目：
- 如果键存在于 `existing_map` → 标记为重复
  - `skip` 策略：保留旧题目
  - `overwrite` 策略：用新题目替换
- 如果键不存在 → 新增题目

## 原子写入实现

```python
def persist_dataset(problems, target_path):
    temp_path = target_path + ".tmp"
    try:
        with open(temp_path, "w") as f:
            json.dump([p.model_dump() for p in problems], f, indent=2)
        os.rename(temp_path, target_path)  # 原子操作
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
```

## 退出码约定

- 0：全部成功
- 1：部分成功（至少有一个成功）
- 2：全部失败或严重错误
- 3：严格模式下任何失败

## 扩展点

未来可添加的导入器：
- `LeetCodeImporter` — 从 LeetCode API 拉取题目
- `LiveCodeBenchImporter` — 从 LiveCodeBench 数据集导入
- `MockPlatformImporter` — 测试用导入器

每个导入器只需实现 `fetch_problems()` 和 `transform_to_schema()`，其余逻辑由基类提供。
