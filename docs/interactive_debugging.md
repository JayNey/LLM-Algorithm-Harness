# 交互式调试模式使用指南

## 概述

交互式调试模式允许您单步执行单个问题的求解过程，实时查看和干预模型推理，以便深入理解模型行为和快速验证策略改进。

## 启动调试会话

### 基本用法

```bash
harness debug --problem <problem_id> --strategy <strategy_name> --model <model_name>
```

### 参数说明

- `--problem`: 要调试的问题 ID（必需）
- `--strategy`: 使用的策略名称，如 `vanilla`、`chain_of_thought`、`multi_round_feedback`（必需）
- `--model`: LLM 模型名称，如 `gpt-4`、`gpt-3.5-turbo`（必需）
- `--trace-output`: 自动导出轨迹的文件路径（可选）
- `--dataset`: 问题数据集路径（可选，默认：`data/problems.json`）

### 示例

```bash
# 调试单个问题
harness debug --problem leetcode_1 --strategy chain_of_thought --model gpt-4

# 自动保存轨迹
harness debug --problem leetcode_1 --strategy vanilla --model gpt-3.5-turbo --trace-output debug_trace.json
```

## 调试器命令参考

### 执行控制

#### `next`
执行下一步并暂停。

```
(debug) next
Executing next step...
```

#### `continue`
继续执行直到遇到下一个断点或完成。

```
(debug) continue
Continuing to next breakpoint...
```

#### `skip`
跳过当前步骤，继续执行下一步。

```
(debug) skip
Skipping current step...
```

### 断点管理

#### `break <location>`
在指定位置启用断点。

可用位置：
- `generate` - 生成代码后
- `execute` - 执行代码前
- `feedback` - 收到反馈后

```
(debug) break generate
✓ Breakpoint enabled at 'generate'
```

#### `unbreak <location>`
禁用指定位置的断点。

```
(debug) unbreak execute
✓ Breakpoint disabled at 'execute'
```

#### `breakpoints`
列出所有已启用的断点。

```
(debug) breakpoints
Enabled breakpoints:
  - generate
  - feedback
```

### Prompt 和参数修改

#### `edit-prompt`
编辑下一轮的 prompt。优先使用 `$EDITOR` 环境变量指定的编辑器，否则使用内联多行输入模式。

```
(debug) edit-prompt
Opening prompt editor...
✓ Prompt modified. New prompt preview:
────────────────────────────────────────────────────────────
Modified prompt content...
────────────────────────────────────────────────────────────
```

#### `set <param> <value>`
动态修改策略参数。

```
(debug) set temperature 0.9
✓ Set temperature = 0.9

(debug) set max_rounds 5
✓ Set max_rounds = 5

(debug) set
Usage: set <param> <value>

Current overrides:
  temperature = 0.9
  max_rounds = 5
```

#### `inject "<text>"`
在下一轮 prompt 末尾注入自定义提示文本。

```
(debug) inject "请特别注意边界情况的处理"
✓ Will inject text into next prompt:
  请特别注意边界情况的处理
```

### 轨迹检查

#### `trace`
显示所有轮次的执行轨迹摘要。

```
(debug) trace
============================================================
Execution Trace Summary
============================================================
Problem: leetcode_1
Strategy: chain_of_thought
Model: gpt-4
Total Rounds: 3

Round 1: Generate → FAILED ✗
Round 2: Execute → PASSED ✓
Round 3: Refine → PASSED ✓
============================================================
```

#### `trace <round_number>`
显示指定轮次的详细信息。

```
(debug) trace 2
============================================================
Round 2 Details
============================================================
Status: PASSED

--- Prompt ---
Problem: Two Sum
...

--- Response ---
Here's my solution...

--- Code ---
def solution(nums, target):
    ...

--- Execution Result ---
Status: PASSED ✓
Passed: 3/3

============================================================
```

#### `export <filepath>`
导出完整轨迹到 JSON 文件。

```
(debug) export debug_session.json
✓ Trace exported to debug_session.json
```

### 状态查看

#### `status`
显示当前调试状态。

```
(debug) status
============================================================
Debugging Status
============================================================
Breakpoints: generate, feedback
Rounds completed: 2
Parameter overrides:
  temperature = 0.9
Prompt modification: pending
============================================================
```

### 退出

#### `exit` / `quit`
退出调试会话。会询问是否保存轨迹。

```
(debug) exit

Save trace before exiting? (y/n): y
Enter filepath (default: trace.json): my_trace.json
✓ Trace saved to my_trace.json

Exiting debug session...
```

## 典型调试工作流

### 1. 理解模型推理过程

```bash
# 启动调试会话
harness debug --problem leetcode_42 --strategy chain_of_thought --model gpt-4

# 在每个关键步骤设置断点
(debug) break generate
(debug) break execute
(debug) break feedback

# 单步执行，观察每一步
(debug) next
# 查看生成的代码
(debug) trace 1

# 继续下一步
(debug) next
```

### 2. 测试参数调整

```bash
# 启动会话
harness debug --problem leetcode_1 --strategy vanilla --model gpt-3.5-turbo

# 修改 temperature 参数
(debug) set temperature 0.2
✓ Set temperature = 0.2

# 执行并观察结果
(debug) next

# 尝试不同的值
(debug) set temperature 0.9
(debug) next
```

### 3. 手动干预 Prompt

```bash
# 启动会话
harness debug --problem leetcode_15 --strategy multi_round_feedback --model gpt-4

# 执行第一轮
(debug) next

# 如果结果不理想，编辑 prompt
(debug) edit-prompt
# 在编辑器中修改 prompt，强调某些约束

# 或注入额外提示
(debug) inject "请使用双指针方法"

# 继续执行
(debug) next
```

### 4. 导出和分析轨迹

```bash
# 启动会话并自动保存
harness debug --problem leetcode_200 --strategy chain_of_thought --model gpt-4 --trace-output analysis.json

# 执行调试...
(debug) next
(debug) next

# 查看轨迹摘要
(debug) trace

# 退出时已自动保存
(debug) exit
```

导出的 JSON 格式：

```json
{
  "problem_id": "leetcode_200",
  "strategy": "chain_of_thought",
  "model": "gpt-4",
  "total_rounds": 3,
  "rounds": [
    {
      "round": 1,
      "prompt": "...",
      "response": "...",
      "code": "...",
      "execution_result": {...},
      "feedback": "...",
      "user_interventions": [
        {
          "type": "set_param",
          "details": "temperature = 0.8"
        }
      ],
      "status": "passed"
    }
  ]
}
```

## 提示和技巧

### 1. 使用外部编辑器

设置 `$EDITOR` 环境变量以使用您喜欢的编辑器：

```bash
export EDITOR=vim
# 或
export EDITOR="code --wait"  # VS Code
```

### 2. 快速查看最近一轮

```bash
(debug) trace $(expr $(rounds) )
```

### 3. 保存常用配置

创建脚本简化启动：

```bash
#!/bin/bash
# debug_leetcode.sh
harness debug \
  --problem "$1" \
  --strategy chain_of_thought \
  --model gpt-4 \
  --trace-output "traces/${1}_$(date +%Y%m%d_%H%M%S).json"
```

使用：
```bash
./debug_leetcode.sh leetcode_42
```

### 4. 对比不同参数

分别运行调试会话，使用不同参数，然后对比导出的轨迹文件。

## 限制和注意事项

1. **单题模式**：调试模式一次只能运行一个问题
2. **固定断点**：断点位置固定在三个关键步骤，不支持任意位置断点
3. **无时间回溯**：无法撤销已执行的步骤
4. **CLI 限制**：仅支持命令行交互，不提供图形界面

## 故障排除

### 问题：编辑器无法打开

**症状**：执行 `edit-prompt` 时显示 "Failed to open external editor"

**解决**：
1. 确认 `$EDITOR` 环境变量已设置：`echo $EDITOR`
2. 测试编辑器命令：`$EDITOR test.txt`
3. 使用内联输入模式作为后备（自动降级）

### 问题：找不到问题 ID

**症状**：启动时显示 "Problem 'xxx' not found"

**解决**：
1. 列出可用问题：检查 `data/problems.json`
2. 确认问题 ID 拼写正确
3. 使用 `--dataset` 指定正确的数据集路径

### 问题：轨迹导出失败

**症状**：`export` 命令显示导出失败

**解决**：
1. 确认目标目录存在且可写
2. 检查文件路径是否合法
3. 确认磁盘空间充足

## 相关资源

- [策略开发指南](../docs/strategy_development.md)
- [批量评估文档](../docs/batch_evaluation.md)
- [问题导入指南](../docs/problem_import.md)

## 反馈和贡献

如有问题或建议，请提交 GitHub Issue 或 Pull Request。
