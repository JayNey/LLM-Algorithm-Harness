## ADDED Requirements

### Requirement: 热图按模型和维度累计真实计数

系统 SHALL 将同模型的全部策略和 repeat 结果按难度/标签累计 solved 和 total，再计算 rate；不得用最后一条覆盖或简单平均各组合比率。行顺序 SHALL 稳定，不改变现有雷达启发式计算或热图字段。

#### Scenario: 不同分母与重复试验
- **WHEN** 同模型同维度的三组合计数分别为 1/1、0/9 和 2/2
- **THEN** 难度和标签热图均为 success=3、total=12、rate=0.25，且乱序输入不改变输出

#### Scenario: 空分母和未知计数
- **WHEN** 某单元格累计 total=0
- **THEN** rate 为 null；某组合缺失或含无效 solved/total 时整个单元格保持未知，不能把缺失当作确定的零或从 rate 推算

#### Scenario: 面板对账
- **WHEN** 从真实 comparison 组合生成实验面板
- **THEN** 热图分子/分母能逐项与 comparison 对账，模型间与标签间不相互覆盖
