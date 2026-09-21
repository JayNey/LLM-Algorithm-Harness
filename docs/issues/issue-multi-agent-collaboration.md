# [创新功能] 协作式求解策略（Multi-Agent）

## 背景与目标

当前策略都是单一 LLM 独立完成任务，缺少协作机制。Multi-Agent 策略模拟真实开发团队的协作模式，让多个 LLM 分别扮演不同角色（算法设计师、代码实现者、测试工程师、代码审查者），研究协作能否提升问题解决率。

- 分类：求解策略（实验性）
- 建议优先级：P3（低优先级，研究性强，成本高）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#12-协作式求解策略)

## 工作范围

### 1. Agent 角色定义
- **算法设计师（Designer）**：
  - 分析问题，识别问题类型
  - 设计算法思路和数据结构
  - 输出：算法描述和伪代码
- **代码实现者（Implementer）**：
  - 将算法转换为 Python 代码
  - 遵循设计师的思路
  - 输出：可执行代码
- **测试工程师（Tester）**：
  - 设计测试用例
  - 执行测试并报告结果
  - 输出：测试报告和失败用例
- **代码审查者（Reviewer）**：
  - 审查代码质量和正确性
  - 提出改进建议
  - 输出：审查意见和优化方向

### 2. 协作流程
- **同步协作模式**（Pipeline）：
  ```
  Designer → Implementer → Tester → Reviewer
  若测试失败，回到 Implementer 修复
  ```
- **异步协作模式**（并行）：
  ```
  Designer 完成后，Implementer 和 Tester 并行工作
  Reviewer 最后汇总并提出改进
  ```

### 3. Agent 通信协议
- 定义结构化消息格式：
  ```json
  {
    "from": "designer",
    "to": "implementer",
    "content": "算法思路描述",
    "artifacts": {"pseudocode": "..."}
  }
  ```
- 维护共享上下文（问题描述、历史消息）
- 支持多轮协作迭代

### 4. 对比实验
- 对比单一模型 vs Multi-Agent 协作：
  - 准确率差异
  - Token 消耗对比（成本分析）
  - 解决复杂问题的能力
- 生成协作效果报告

## 验收标准

- [ ] 实现 4 个 Agent 角色类
- [ ] 同步和异步协作模式都能正常运行
- [ ] Agent 之间消息传递正确
- [ ] 完整记录协作过程和决策链
- [ ] 对比实验显示协作的成本效益
- [ ] 文档更新：Multi-Agent 策略说明

## 边界

- 所有 Agent 使用相同的基础模型（如 GPT-4）
- 不涉及异构模型协作（不同供应商混合）
- 协作轮次上限：3 轮（避免成本失控）

## 依赖与关联

- 前置：#14 [功能] 可复用评测任务服务（已完成）
- 前置：#15 [功能] 固定预算实验（需要成本控制）
- 关联：代码质量评估（Reviewer Agent 可调用）

## 技术要点

### Agent 基类
```python
class Agent:
    def __init__(self, role: str, llm_client: LLMClient):
        self.role = role
        self.llm = llm_client
        self.context = []
    
    def process(self, message: dict) -> dict:
        # 子类实现具体逻辑
        pass

class DesignerAgent(Agent):
    def process(self, message):
        prompt = f"作为算法设计师，分析问题：{message['problem']}"
        response = self.llm.generate(prompt)
        return {
            'from': 'designer',
            'to': 'implementer',
            'content': response
        }
```

### 协作编排
```python
class MultiAgentStrategy(StrategyBase):
    def solve(self, problem):
        # 1. Designer 分析
        design = self.designer.process({'problem': problem.description})
        
        # 2. Implementer 实现
        code = self.implementer.process(design)
        
        # 3. Tester 测试
        test_result = self.tester.test(code, problem.public_tests)
        
        if test_result.failed:
            # 4. 反馈给 Implementer 修复
            code = self.implementer.fix(test_result.errors)
        
        # 5. Reviewer 审查
        review = self.reviewer.review(code)
        
        return code
```

## 预期收益

- 实现工作量：约 10-14 天
- 研究价值：探索 LLM 协作的潜力
- 学术价值：可发表论文（Multi-Agent 系统）
- 实际效果：**不确定**（需要实验验证）

## 风险与挑战

1. **成本高**：4 个 Agent × 多轮 = 高昂的 Token 消耗
2. **效果不确定**：协作可能引入更多错误
3. **复杂度高**：Agent 交互逻辑复杂，调试困难

## 建议

**延后实现**，理由：
- 研究性功能，实际收益不确定
- 成本高，不适合日常评估
- 优先实现确定性更高的功能
