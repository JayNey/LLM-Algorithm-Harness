## 问题描述

PR#68 的代码审查发现两个 blocker 级别的问题，必须在合并前修复：

1. **温度参数硬编码**：`src/strategies/self_consistency.py:90` 处将温度参数硬编码为 0.8，违反了 Issue #47 的验收标准"支持温度参数配置以增加候选解的多样性"
2. **策略未导出**：`src/strategies/__init__.py` 仅包含一行注释，未导出 `SelfConsistencyStrategy` 类，违反项目规范要求新策略应在策略工厂中注册

## 根因分析

### 根因 1：温度参数硬编码
在实现 Self-Consistency 策略时，为了保证候选解的多样性，直接在代码中硬编码了 `temperature=0.8`：

```python
llm_response = self.llm_client.generate(
    base_prompt,
    system_prompt=self.config.system_prompt,
    temperature=0.8,  # 硬编码
    max_tokens=(...),
    custom_params=self.config.custom_params,
)
```

这导致用户无法通过配置文件自定义温度参数，不符合策略参数化配置的设计原则。

### 根因 2：策略未导出
`src/strategies/__init__.py` 文件只有一行文档字符串，没有导出任何策略类。虽然 `src/harness.py` 中直接导入了 `SelfConsistencyStrategy`，但缺少统一的策略导出点不符合 Python 包的最佳实践。

## 修复目标

1. 将温度参数改为可配置，从 `custom_params` 读取，默认值保持 0.8
2. 在 `src/strategies/__init__.py` 中导出所有策略类，包括新增的 `SelfConsistencyStrategy`
3. 更新 README.md 中的配置示例，说明温度参数可配置
4. 确保修复后所有现有测试仍然通过
