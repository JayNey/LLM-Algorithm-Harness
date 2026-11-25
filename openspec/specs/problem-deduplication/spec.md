# problem-deduplication Specification

## Purpose
提供题目去重能力，通过相似度检测和指纹匹配识别重复题目，并支持交互式或自动化的合并操作。

## Requirements

### Requirement: 相似度检测

系统 SHALL 使用 TF-IDF 向量化和余弦相似度算法检测文本相似的题目。

#### Scenario: 检测高度相似题目
- **WHEN** 两个题目的标题和描述余弦相似度 > 0.9
- **THEN** 系统标记为疑似重复题目

#### Scenario: 不同题目不被误判
- **WHEN** 两个题目的余弦相似度 <= 0.9
- **THEN** 系统不标记为重复

### Requirement: 指纹匹配

系统 SHALL 基于 `source_platform + source_problem_id` 生成唯一指纹，检测完全相同的题目。

#### Scenario: 检测完全相同题目
- **WHEN** 两个题目具有相同的 `source_platform` 和 `source_problem_id`
- **THEN** 系统标记为完全重复题目

#### Scenario: 处理缺失来源信息
- **WHEN** 题目缺少 `source_platform` 或 `source_problem_id`
- **THEN** 系统跳过指纹匹配，仅依赖相似度检测

### Requirement: 去重命令

系统 SHALL 提供 `harness problems deduplicate` CLI 命令，支持以下参数：
- `--dataset <path>` — 数据集路径（默认：data/problems.json）
- `--threshold <float>` — 相似度阈值（默认：0.9）
- `--auto-merge` — 自动合并重复题目，不提示用户
- `--dry-run` — 仅显示重复题目，不执行合并

#### Scenario: 交互式去重
- **WHEN** 用户运行 `harness problems deduplicate --dataset data/problems.json`
- **THEN** 系统显示所有重复题目对，并提示用户选择保留或合并

#### Scenario: 自动去重
- **WHEN** 用户运行 `harness problems deduplicate --dataset data/problems.json --auto-merge`
- **THEN** 系统自动合并所有重复题目，保留第一个出现的版本

#### Scenario: 预览模式
- **WHEN** 用户运行 `harness problems deduplicate --dataset data/problems.json --dry-run`
- **THEN** 系统仅输出重复题目列表，不修改数据集文件

### Requirement: 合并策略

系统 SHALL 在合并重复题目时保留更完整的题目信息。

#### Scenario: 合并时保留完整信息
- **WHEN** 两个重复题目被合并
- **THEN** 系统保留字段更完整的题目作为主版本，并合并标签、测试用例等列表字段

#### Scenario: 记录合并历史
- **WHEN** 题目被合并
- **THEN** 系统在保留的题目中添加 `merged_from` 字段，记录被合并题目的 ID

### Requirement: 去重报告

系统 SHALL 输出详细的去重报告，包括检测到的重复题目数量、合并操作数量和跳过的题目数量。

#### Scenario: 显示去重统计
- **WHEN** 去重命令执行完成
- **THEN** 系统输出报告，包含：
  - 扫描的题目总数
  - 通过相似度检测发现的重复对数
  - 通过指纹匹配发现的重复对数
  - 实际合并的题目数量
  - 用户跳过的题目数量

### Requirement: 单元测试覆盖

去重核心逻辑 SHALL 有完整的单元测试覆盖。

#### Scenario: 测试相似度计算
- **WHEN** 运行单元测试
- **THEN** 测试验证 TF-IDF 和余弦相似度计算的准确性

#### Scenario: 测试指纹生成
- **WHEN** 运行单元测试
- **THEN** 测试验证指纹生成和匹配逻辑的正确性

#### Scenario: 测试合并策略
- **WHEN** 运行单元测试
- **THEN** 测试验证合并逻辑保留完整信息并正确记录历史

### Requirement: 个人题库相似题只读预览

系统 SHALL 允许已认证用户扫描本人的个人题库，使用与 CLI 一致的来源指纹匹配、TF-IDF 和余弦相似度规则。文本阈值 MUST 为 0 到 1 的有限数，默认 0.9；只有严格超过阈值的文本对被标记。预览 MUST 返回不重叠的候选组、题目 ID、来源、匹配依据、相似度及各保留题选择对应的完整合并结果，且不写入源库。

#### Scenario: 预览候选与字段变化
- **WHEN** 本人题库包含相同来源指纹或文本超过阈值的题目
- **THEN** 系统列出候选组、实际匹配边及推荐保留题，并提供原题和可审核的合并结果
- **AND** 扫描前后的源库内容和修订不变

#### Scenario: 空库、无候选和不可向量化文本
- **WHEN** 题库为空、没有重复项，或文本为空及仅包含停用词
- **THEN** 系统返回真实的候选结果；不可向量化文本不使来源指纹检测失败

### Requirement: 只保存批准的相似题合并

系统 SHALL 只应用用户明确提交的候选组与保留题选择，拒绝未知组、重复组和组外保留题。合并 MUST 保留选定题的 ID、正文和非列表元数据，按 CLI 规则去重合并标签与测试列表，记录被合并 ID。新版本 MUST 包含未批准组的全部原题及未分组原题；零批准组不得创建版本。

#### Scenario: 保留题切换及跳过组
- **WHEN** 用户在第一组选择非推荐题作为保留题，并跳过第二组
- **THEN** 新版本仅从第一组移除被合并题，保存与该保留题预览一致的内容及合并 ID，第二组保持原样

#### Scenario: 伪造审核选择
- **WHEN** 请求包含组外题、未知组或同一组的多份选择
- **THEN** API 拒绝整个请求且不保存任何版本

### Requirement: 合并确认的修订与幂等边界

系统 MUST 将预览绑定当前所有者、源库修订、阈值及候选结果，并在保存事务中重新校验源库。源库变化后的新确认 MUST 返回冲突并要求重新扫描。一次相同确认的重试和并发提交 MUST 只保存一个版本并返回同一版本；已完成确认的重试不得再次应用合并。

#### Scenario: 预览后库发生变化
- **WHEN** 扫描后导入或覆盖了源库，再提交尚未保存的确认
- **THEN** 保存返回冲突且不创建版本，用户需要重新扫描并审核

#### Scenario: 重复和并发提交
- **WHEN** 同一账号重复或并发提交相同预览、名称和组选择
- **THEN** 仅生成一个版本，各次成功响应返回同一版本 ID

#### Scenario: 跨账号或未认证访问
- **WHEN** 未认证请求扫描或保存，或另一账号提交他人的预览令牌或请求其版本
- **THEN** API 拒绝请求，且不泄露他人题库内容

### Requirement: 合并版本兼容已有引用

系统 SHALL 通过既有个人版本入口重新读取合并结果并创建评估，保留评估实际使用的正文与元数据。合并 MUST NOT 改写源题库、历史评估、已保存题集及旧版本中的题目引用。

#### Scenario: 新版本用于评估且旧引用可访问
- **WHEN** 用户保存合并版本后重新打开它并创建评估
- **THEN** 评估使用新版本的保留题及其审核内容，旧结果、已有题集和旧版本仍可打开
