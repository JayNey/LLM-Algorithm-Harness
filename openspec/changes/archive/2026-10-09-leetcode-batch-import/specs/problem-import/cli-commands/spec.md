# problem-import/cli-commands Delta Specification

## MODIFIED Requirements

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

## ADDED Requirements

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
