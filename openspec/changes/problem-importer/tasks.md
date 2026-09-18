# Tasks: 可扩展题库导入器

## Task 1: 创建 ProblemImporter 抽象基类

**文件**: `src/importers/base.py`

创建导入器抽象基类，定义标准接口：

- [x] 定义 `ProblemImporter` 抽象基类
- [x] 实现抽象方法签名：
  - `fetch_problems()` — 返回原始数据
  - `transform_to_schema(raw_data)` — 返回 `List[Problem]`
  - `detect_duplicates(problems, existing)` — 返回去重结果
  - `generate_report(results)` — 返回报告字典
- [x] 实现基类通用方法：
  - `validate_problems(problems)` — 调用 `validators.validate_problem_schema`
  - `persist_dataset(problems, path)` — 原子写入（临时文件 + 重命名）
- [x] 添加类型注解和文档字符串

## Task 2: 实现 LocalJsonImporter

**文件**: `src/importers/local_json.py`

将现有本地 JSON 加载逻辑重构为导入器：

- [x] 创建 `LocalJsonImporter` 类，继承 `ProblemImporter`
- [x] 实现 `fetch_problems(file_path)` — 读取 JSON 文件
- [x] 实现 `transform_to_schema(raw_data)` — 解析为 `Problem` 对象
- [x] 实现 `detect_duplicates()` — 基于 `(source_platform, source_problem_id)` 去重
- [x] 实现 `generate_report()` — 生成导入报告
- [x] 处理部分成功场景（单题失败不影响其他）
- [x] 添加单元测试

## Task 3: 添加 CLI import 子命令

**文件**: `src/main.py`

在现有 CLI 中添加 `import` 子命令：

- [x] 定义 `import` 子命令参数：
  - `--source` (必需)
  - `--input` (必需)
  - `--output` (可选，默认 `data/problems.json`)
  - `--preview` (标志)
  - `--update-strategy` (可选，默认 `skip`)
  - `--force` (标志)
- [x] 实现导入流程：
  1. 根据 `--source` 实例化导入器
  2. 加载现有数据集
  3. 拉取、转换、校验新题目
  4. 检测重复
  5. 显示导入摘要
  6. 确认（非预览、非 force 模式）
  7. 持久化（非预览模式）
  8. 显示导入报告
- [x] 实现预览模式标识输出
- [x] 实现退出码约定（0/1/2/3）

## Task 4: 实现去重逻辑

**文件**: `src/importers/base.py` (或独立工具模块)

实现基于平台和题号的去重检测：

- [x] 创建 `detect_duplicates()` 方法
- [x] 使用 `(source_platform, source_problem_id)` 作为去重键
- [x] 构建现有题目映射
- [x] 对比新题目，标记重复
- [x] 根据 `update_strategy` 决定保留或覆盖
- [x] 返回去重结果（新增、跳过、覆盖列表）

## Task 5: 实现原子写入

**文件**: `src/importers/base.py`

确保数据集写入的原子性：

- [x] 实现 `persist_dataset(problems, target_path)` 方法
- [x] 先写入临时文件（`target_path + ".tmp"`）
- [x] 使用 `os.rename()` 原子替换
- [x] 异常处理：清理临时文件，保留原文件
- [x] 添加错误日志

## Task 6: 创建 MockPlatformImporter

**文件**: `src/importers/mock.py`

创建测试用导入器：

- [x] 创建 `MockPlatformImporter` 类
- [x] 实现所有抽象方法
- [x] 生成测试用题目数据
- [x] 用于集成测试和示例

## Task 7: 添加集成测试

**文件**: `tests/test_importers.py`

测试完整导入流程：

- [x] 测试本地 JSON 导入
- [x] 测试预览模式（不写入）
- [x] 测试去重逻辑（skip 和 overwrite 策略）
- [x] 测试部分成功场景
- [x] 测试原子写入（模拟写入失败）
- [x] 测试 CLI 命令参数解析
- [x] 测试退出码

## Task 8: 更新文档

**文件**: `README.md`, 新增 `docs/importing.md`

更新用户文档：

- [x] 在 README.md 中添加导入功能说明
- [x] 创建 `docs/importing.md` 详细文档
- [x] 提供使用示例
- [x] 说明如何创建自定义导入器
- [x] 列出支持的来源类型
