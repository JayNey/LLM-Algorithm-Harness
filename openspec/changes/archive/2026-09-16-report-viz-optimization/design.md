## Context

当前 `ChartGenerator` 使用 matplotlib 生成三类图表：成功率柱状图、token 消耗折线图、迭代次数直方图。`HTMLGenerator` 调用这些方法并将返回的 BytesIO 对象编码为 base64 嵌入 HTML。

现有问题：
1. 图表生成方法缺少内部错误处理，matplotlib 异常会直接传播
2. HTMLGenerator 的 try-catch 块捕获异常但仅打印错误，未影响到最终生成的 HTML
3. Token 图表只显示平均值，未展示分布范围
4. 缺少成本估算能力，用户无法直观了解经济成本
5. 迭代次数直方图多策略重叠时难以对比

## Goals / Non-Goals

**Goals:**
- 确保单个图表失败不中断整体报告生成
- Token 图表增加误差线（25%/75% 分位数）展示分布
- Token 图表增加双 Y 轴显示成本估算
- 迭代次数图改为分组柱状图提升可读性
- 保持现有 API 兼容性，不改变调用方式

**Non-Goals:**
- 不修改 ExecutionResult、Judge、Problem 等核心评测数据结构
- 不改变 Markdown/CSV 报告格式
- 不支持交互式图表（保持静态 PNG）
- 不增加新的图表类型

## Decisions

### Decision 1: 错误处理策略 - 返回 Optional[BytesIO]

**选择：** ChartGenerator 方法返回 `Optional[io.BytesIO]`，失败时返回 None

**理由：**
- 调用方可通过返回值判断成功/失败，无需捕获异常
- 保持方法签名简洁，不引入自定义异常类型
- HTMLGenerator 可统一处理 None 值，插入错误提示

**替代方案：**
- 抛出自定义异常：增加复杂度，调用方需 try-catch 每个方法
- 返回默认空白图片：隐藏错误，不利于调试

### Decision 2: Token 分位数计算 - 基于原始数据而非聚合指标

**选择：** 修改 `generate_token_chart` 接收 `results: Dict[str, List[ExecutionResult]]` 而非仅 `metrics: Dict[str, Dict]`

**理由：**
- metrics 只包含平均值等聚合统计，无法计算分位数
- 需要访问原始每个问题的 token 数据才能计算 25%/75% 分位数
- HTMLGenerator 已有 results 参数，传递成本低

**替代方案：**
- 在 metrics 计算阶段预先计算分位数：耦合度高，增加 metrics 计算复杂度

### Decision 3: 成本估算 - 内置常见模型定价 + 默认值

**选择：** 在 ChartGenerator 中维护常见模型定价字典，未知模型使用保守默认值

**理由：**
- 用户大多使用主流模型（GPT-4、Claude、Gemini），内置定价覆盖常见场景
- 默认值避免未知模型时无法显示成本
- 定价字典易于维护和更新

**定价来源：** 2026年9月主流模型官方定价
- GPT-4: $30/M input, $60/M output
- GPT-3.5: $0.5/M input, $1.5/M output  
- Claude 3.5 Sonnet: $3/M input, $15/M output
- Gemini 1.5 Pro: $1.25/M input, $5/M output
- 默认: $10/M input, $30/M output

**替代方案：**
- 从配置文件读取：过度设计，大多数用户不需要自定义
- API 动态查询定价：增加网络依赖和延迟

### Decision 4: 双 Y 轴实现 - twinx() + 不同颜色标识

**选择：** 使用 matplotlib 的 `ax.twinx()` 创建共享 X 轴的双 Y 轴

**理由：**
- matplotlib 原生支持，成熟稳定
- 左轴显示 tokens（蓝色），右轴显示成本（绿色），颜色区分清晰
- 图例明确标注两条曲线含义

**替代方案：**
- 两张独立图表：浪费空间，不利于对比
- 单 Y 轴归一化：失去实际数值的直观性

### Decision 5: 迭代次数图 - 分组柱状图替代重叠直方图

**选择：** 使用 `ax.bar()` + 手动计算分组位置，每个策略一种颜色

**理由：**
- 直方图（`ax.hist`）alpha 混合时颜色难以区分
- 分组柱状图并排显示，对比更直观
- 迭代次数通常 1-10 范围内，分组数量可控

**实现细节：**
- X 轴刻度为迭代次数（1, 2, 3...）
- 每个迭代次数位置下，策略柱子并排排列
- 使用 `width / num_strategies` 计算每个柱子宽度和偏移

**替代方案：**
- 保持直方图增加透明度：多策略时仍难以区分

## Risks / Trade-offs

### Risk 1: 分位数计算增加内存占用

**风险：** 传递完整 results 到 chart 方法，大规模评测时内存占用增加

**缓解：** 
- 仅传递必要的 token 数据而非完整 ExecutionResult 对象
- 实际评测规模通常 < 100 问题 × 5 策略，内存影响可控（< 1MB）

### Risk 2: 内置定价过时

**风险：** LLM 定价频繁变动，内置定价可能过时导致成本估算不准

**缓解：**
- 在图表标题或图例中标注"估算值"
- 文档说明定价更新日期
- 未来可通过配置文件覆盖

### Risk 3: 缺少输入输出 token 分离时估算不准

**风险：** 现有 ExecutionResult 可能只记录总 token 数，无法区分输入输出

**缓解：**
- 使用 70%/30% 输入输出比例作为保守估算（行业常见比例）
- 优先使用 prompt_tokens/completion_tokens 字段（如果存在）
- 在成本图例中标注"基于估算比例"
