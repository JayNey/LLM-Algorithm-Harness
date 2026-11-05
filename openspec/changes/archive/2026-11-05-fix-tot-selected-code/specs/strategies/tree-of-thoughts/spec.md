## MODIFIED Requirements

### Requirement: Solution extraction
策略 SHALL 从已探索分支中选择含非空白代码的最高分叶子，并在最终结果中保存同一份代码。

#### Scenario: Return highest scoring leaf
- **WHEN** 搜索完成或达到 max_depth，不论单层或多层、BFS 或 DFS、兄弟遍历顺序
- **THEN** generated_code 等于所选最高分有效叶子的代码，公开或反馈执行使用同一份代码

#### Scenario: Handle no valid solution
- **WHEN** 没有叶子、所有分支被剪枝且没有有效叶子代码，或所有叶子代码为空白
- **THEN** 返回失败，failure_category 为 code_extraction_failed，generated_code 为空，不执行空代码

#### Scenario: Hidden evaluation uses selected code
- **WHEN** ToT 公开测试通过且题目含隐藏用例
- **THEN** Harness 使用结果中同一份所选代码执行 hidden，隐藏失败时最终结果必须失败

#### Scenario: Preserve selected code on execution failure
- **WHEN** 所选代码公开执行失败或沙箱异常
- **THEN** 结果保持失败并保存所选代码，执行结果可用时予以保留
