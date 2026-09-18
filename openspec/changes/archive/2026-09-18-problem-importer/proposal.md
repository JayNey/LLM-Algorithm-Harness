## Why

用户目前必须手工维护 `problems.json`，缺少平台适配接口与导入报告。新增题库平台时无法复用统一的规范化和校验流程，导致题库扩展成本高且容易出错。建立可扩展的导入器架构，使题库来源可插拔，并提供预览、校验、去重等安全机制。

## What Changes

- 定义标准导入器接口（`ProblemImporter` 抽象基类），规范拉取/读取来源 → 转换题目 Schema → 校验 → 生成导入报告 → 持久化的完整流程
- 提供 CLI 导入入口（`import` 子命令），支持预览模式、批量输入、来源标识、重复题检测和明确的更新/跳过策略
- 按平台与稳定题号识别题目，记录导入时间、源版本/内容摘要及解析警告
- 原子写入数据集：单题解析失败不丢失其他成功项；严格模式与部分成功状态要有清晰退出码
- 将现有本地 JSON 加载重构为 `LocalJsonImporter`，与新增平台适配器走同一导入接口
- 提供测试用适配器示例（如 `MockPlatformImporter`）

## Capabilities

### New Capabilities

- `problem-import/importer-interface`: 定义可扩展的题库导入器接口，包括标准化的拉取、转换、校验、去重、报告生成和持久化流程
- `problem-import/cli-commands`: 提供 CLI 导入入口，支持预览模式、批量操作、来源标识、更新策略和详细的导入报告

### Modified Capabilities

无。本次变更引入新的导入能力，不修改现有 spec 的行为要求。

## Impact

**代码影响：**
- `src/problem_loader.py` — 重构为基于导入器接口的加载逻辑，保留向后兼容的 `load()` 方法
- `src/models.py` — 可能增加导入元数据字段（如 `imported_at`、`source_version`、`import_warnings`）
- `src/main.py` — 新增 `import` 子命令入口
- 新增 `src/importers/` 目录 — 包含基类、本地 JSON 适配器、测试适配器及未来的平台适配器

**数据影响：**
- 导入报告（JSON 格式）记录成功/失败项、重复检测结果、警告信息
- `problems.json` 写入改为原子操作（临时文件 + 重命名）

**用户体验：**
- 预览模式让用户在实际写入前查看导入结果
- 明确的更新策略（跳过/覆盖）防止意外数据丢失
- 详细的导入报告帮助定位解析失败的题目

**边界：**
- 本 issue 不包含 LeetCode/LiveCodeBench 的具体网络抓取实现
- 不默认批量覆盖用户题库，所有写入操作需明确确认或使用 `--force` 标志
