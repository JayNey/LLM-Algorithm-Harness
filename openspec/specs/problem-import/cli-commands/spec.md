# problem-import/cli-commands Specification

## Purpose
提供 CLI 导入入口，让用户通过命令行安全地从不同来源导入题目，支持预览模式、批量操作、来源标识、更新策略和详细的导入报告。

## Requirements

### Requirement: 提供 import 子命令

CLI SHALL 提供 `import` 子命令，支持以下参数：
- `--source <type>` — 导入来源类型（local-json, leetcode, codeforces, livecodebench, mock 等）
- `--input <path>` — 输入路径（文件路径、目录或 URL）；对 leetcode 批量导入可选
- `--output <path>` — 输出数据集路径（默认：data/problems.json）
- `--preview` — 预览模式，不实际写入
- `--update-strategy <skip|overwrite>` — 重复题目的更新策略（默认：skip）
- `--force` — 跳过确认提示，直接执行
- `--tags <tag>...` — 按标签过滤题目（适用于 leetcode, codeforces, livecodebench）
- `--import-difficulty <easy|medium|hard>` — 按难度过滤题目（适用于 leetcode, livecodebench）
- `--import-limit <n>` — 限制导入题目数量（适用于 leetcode, codeforces, livecodebench）

#### Scenario: 基本导入命令

- **WHEN** 用户运行 `harness import --source local-json --input data/new_problems.json`
- **THEN** 系统从指定 JSON 文件导入题目到默认数据集路径

#### Scenario: 指定输出路径

- **WHEN** 用户运行 `harness import --source local-json --input data/new.json --output data/custom.json`
- **THEN** 系统导入题目到指定的输出路径

#### Scenario: LeetCode 按标签批量导入

- **WHEN** 用户运行 `harness import --source leetcode --tags dynamic-programming --import-limit 20`
- **THEN** 系统从 LeetCode 获取标签为 "dynamic-programming" 的题目列表（最多 20 题），逐题抓取详情并导入

#### Scenario: LeetCode 按难度和标签过滤

- **WHEN** 用户运行 `harness import --source leetcode --tags graph --import-difficulty medium --import-limit 10`
- **THEN** 系统导入标签为 "graph"、难度为 "medium" 的题目（最多 10 题）

#### Scenario: LeetCode 单题导入保持兼容

- **WHEN** 用户运行 `harness import --source leetcode --input https://leetcode.com/problems/two-sum/`
- **THEN** 系统只导入该单个题目，批量参数（tags、difficulty、limit）被忽略

### Requirement: 预览模式不修改数据集

预览模式 SHALL 执行完整的导入流程（拉取、转换、校验、去重），但不写入目标数据集。

#### Scenario: 预览导入结果

- **WHEN** 用户运行 `harness import --source local-json --input data/new.json --preview`
- **THEN** 系统显示导入报告（成功、失败、重复题目统计），但不修改 `data/problems.json`

#### Scenario: 预览模式标识清晰

- **WHEN** 使用预览模式导入
- **THEN** 命令输出明确标识 `[PREVIEW MODE]`，并提示 "No changes were made to the dataset"

### Requirement: 重复题目更新策略

用户 SHALL 通过 `--update-strategy` 指定重复题目的处理方式：
- `skip`（默认）：跳过重复题目，保留已有版本
- `overwrite`：覆盖重复题目，使用新版本

#### Scenario: 默认跳过重复题目

- **WHEN** 导入的题目与已有题目重复，且未指定更新策略
- **THEN** 系统跳过该题目，保留原有版本，并在报告中记录

#### Scenario: 覆盖重复题目

- **WHEN** 用户运行 `harness import --source local-json --input data/new.json --update-strategy overwrite`
- **THEN** 系统用新版本覆盖重复题目，并在报告中记录覆盖的题目 ID

### Requirement: 明确的来源标识

导入命令 SHALL 要求用户明确指定 `--source` 参数，标识题目来源类型。

#### Scenario: 缺少来源参数报错

- **WHEN** 用户运行 `harness import --input data/new.json` 但未指定 `--source`
- **THEN** 命令返回错误，提示 "Error: --source is required"

#### Scenario: 不支持的来源类型报错

- **WHEN** 用户指定未注册的来源类型（如 `--source unknown`）
- **THEN** 命令返回错误，列出支持的来源类型

### Requirement: 交互式确认

导入命令 SHALL 在实际写入前显示导入摘要，并要求用户确认（除非使用 `--force`）。

#### Scenario: 导入前显示摘要并确认

- **WHEN** 用户运行导入命令（非预览、非 force 模式）
- **THEN** 系统显示导入摘要（将导入 X 个题目，跳过 Y 个重复），并提示 "Proceed with import? (y/N)"

#### Scenario: 用户拒绝确认

- **WHEN** 用户在确认提示中输入 "N" 或直接回车
- **THEN** 系统取消导入，不修改数据集，退出码为 0

#### Scenario: force 模式跳过确认

- **WHEN** 用户运行 `harness import --source local-json --input data/new.json --force`
- **THEN** 系统跳过确认提示，直接执行导入

### Requirement: 批量导入参数对支持的来源生效

`--tags`、`--import-difficulty`、`--import-limit` 参数 SHALL 对支持批量导入的来源（leetcode, codeforces, livecodebench）生效。

#### Scenario: 不支持批量的来源忽略批量参数

- **WHEN** 用户运行 `harness import --source local-json --input data/new.json --tags graph`
- **THEN** 系统忽略 `--tags` 参数，按正常流程导入本地 JSON 文件

#### Scenario: LeetCode 批量导入需要至少一个过滤条件

- **WHEN** 用户运行 `harness import --source leetcode` 且未提供 `--input`、`--tags`、`--import-difficulty` 中的任何一个
- **THEN** 命令返回错误，提示 "Error: LeetCode batch import requires --tags, --import-difficulty, or --input (URL/slug)"

### Requirement: 批量导入显示进度

当批量导入多个题目时，CLI SHALL 显示导入进度，包括当前题目编号和总题目数。

#### Scenario: 批量导入显示进度信息

- **WHEN** 用户批量导入 20 个 LeetCode 题目
- **THEN** 系统在抓取每个题目详情时显示 "Fetching problem 3/20: two-sum"

#### Scenario: 单题导入不显示进度

- **WHEN** 用户导入单个题目
- **THEN** 系统不显示进度信息，只显示最终导入报告
