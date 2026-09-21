# [功能] 交互式问题调试模式

## 背景与目标

当前批量评估模式只能查看最终结果，缺少逐步调试能力。交互式调试模式允许单独运行某个题目，逐步查看模型推理过程，手动干预和调整参数，帮助深入理解模型行为和快速验证改进方案。

- 分类：开发工具
- 建议优先级：P2（中等价值，提升开发体验）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#10-交互式问题调试模式)

## 工作范围

### 1. 单题运行模式
- CLI 交互命令：
  ```bash
  harness debug --problem leetcode_1 --strategy cot --model gpt-4
  ```
- 逐步显示执行过程：
  - 每轮迭代的 prompt
  - LLM 响应内容
  - 代码执行结果
  - 测试用例反馈

### 2. 断点和单步执行
- 支持在策略关键步骤暂停：
  - 生成代码后暂停
  - 执行测试前暂停
  - 收到反馈后暂停
- 单步执行命令：
  - `next` - 执行下一步
  - `continue` - 继续到断点
  - `skip` - 跳过当前步骤

### 3. 手动干预
- 实时调整 prompt：
  ```
  > edit-prompt
  [打开编辑器修改下一轮 prompt]
  ```
- 修改策略参数：
  ```
  > set temperature 0.9
  > set max_rounds 5
  ```
- 插入自定义提示：
  ```
  > inject "请注意边界情况的处理"
  ```

### 4. 执行轨迹可视化
- 显示推理链路：
  ```
  Round 1: Generate → Execute → Failed
    Error: IndexError at line 5
  Round 2: Generate (with feedback) → Execute → Passed sample
    Hidden test: Failed (output mismatch)
  Round 3: Refine → Execute → All passed
  ```
- 保存完整轨迹到文件：
  ```bash
  harness debug --problem leetcode_1 --trace-output trace.json
  ```

## 验收标准

- [ ] CLI 支持 `harness debug` 命令
- [ ] 可逐步查看每轮的 prompt、response、执行结果
- [ ] 支持断点和单步执行
- [ ] 可实时修改 prompt 和参数
- [ ] 执行轨迹完整记录并可导出
- [ ] 文档更新：交互式调试使用指南

## 边界

- 仅支持 CLI 交互，不实现图形化 debugger
- 不支持时间回溯（无法撤销执行）
- 断点位置固定在策略关键步骤，不支持任意位置断点

## 依赖与关联

- 前置：#13 [修复] 完整保存失败结果（已完成，复用轨迹记录）
- 关联：增强的错误分析（调试模式可查看详细错误）
- 后续扩展：图形化 debugger（Web UI）

## 技术要点

### CLI 交互循环
```python
def debug_loop(problem, strategy):
    while not strategy.is_complete():
        action = input("Command (next/edit/set/inject): ")
        
        if action == 'next':
            result = strategy.step()
            display_result(result)
        elif action.startswith('set'):
            _, param, value = action.split()
            strategy.set_param(param, value)
        elif action == 'edit':
            new_prompt = open_editor(strategy.current_prompt)
            strategy.override_prompt(new_prompt)
```

### 断点管理
```python
class DebugStrategy(StrategyBase):
    def generate_code(self, prompt):
        if self.breakpoint_enabled:
            input("Breakpoint: Before generation (press Enter)")
        return super().generate_code(prompt)
```

### 轨迹导出
```python
trace = {
    'problem_id': problem.id,
    'rounds': [
        {
            'round': 1,
            'prompt': "...",
            'response': "...",
            'execution': {"status": "failed", "error": "..."},
            'user_intervention': None
        },
        # ...
    ]
}
json.dump(trace, open('trace.json', 'w'))
```

## 预期收益

- 实现工作量：约 5-7 天
- 开发效率：快速验证策略改进想法
- 用户体验：深入理解模型推理过程
- 教学价值：适合演示和教学场景
