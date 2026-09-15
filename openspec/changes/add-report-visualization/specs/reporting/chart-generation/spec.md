## Purpose

使用 matplotlib 生成可视化图表，展示策略性能对比、资源消耗趋势和分布统计。

## ADDED Requirements

### Requirement: 生成成功率对比柱状图

系统 SHALL 生成展示各策略成功率的垂直柱状图。

#### Scenario: 基础柱状图生成
- **WHEN** 用户调用 ChartGenerator.generate_success_rate_chart() 并传入策略指标字典
- **THEN** 系统生成 PNG 图片，X 轴为策略名称，Y 轴为成功率（0-100%），每个策略显示为一个柱形

#### Scenario: 柱形颜色编码
- **WHEN** 生成成功率柱状图
- **THEN** 成功率 ≥80% 的柱形显示为绿色，50-80% 显示为黄色，<50% 显示为红色

#### Scenario: 数值标注
- **WHEN** 生成柱状图
- **THEN** 每个柱形顶部标注精确的成功率百分比（保留 1 位小数）

### Requirement: 生成 Token 消耗折线图

系统 SHALL 生成展示各策略 Token 消耗统计的折线图。

#### Scenario: 基础折线图生成
- **WHEN** 用户调用 ChartGenerator.generate_token_chart() 并传入策略指标字典
- **THEN** 系统生成 PNG 图片，X 轴为策略名称，Y 轴为平均 Token 消耗，每个策略用不同颜色的线条和标记点表示

#### Scenario: 显示 Token 分位数
- **WHEN** 策略指标包含 token_percentiles 数据（p50、p90、p99）
- **THEN** 图表在每个策略位置显示误差线，表示 p50 到 p90 的范围

#### Scenario: 双 Y 轴显示
- **WHEN** 同时展示平均 Token 和成本估算
- **THEN** 左侧 Y 轴显示 Token 数量，右侧 Y 轴显示美元成本（基于 GPT-3.5 定价）

### Requirement: 生成迭代次数分布图

系统 SHALL 生成展示多轮策略迭代次数分布的直方图。

#### Scenario: 基础直方图生成
- **WHEN** 用户调用 ChartGenerator.generate_iteration_distribution() 并传入包含多轮策略的结果列表
- **THEN** 系统生成 PNG 图片，X 轴为迭代次数（1, 2, 3, ...），Y 轴为问题数量，显示迭代次数的频率分布

#### Scenario: 多策略对比
- **WHEN** 传入多个多轮策略的结果
- **THEN** 图表使用分组柱状图或堆叠柱状图，区分不同策略的分布

#### Scenario: 仅单轮策略时的处理
- **WHEN** 所有策略的 iterations 均为 1
- **THEN** 系统返回空图表或提示信息 "No multi-round strategies"

### Requirement: 图表样式和格式

生成的图表 SHALL 遵循一致的样式规范，确保可读性和专业外观。

#### Scenario: 图表尺寸和分辨率
- **WHEN** 生成任何图表
- **THEN** 图表尺寸为 10x6 英寸，DPI 为 100，确保清晰度

#### Scenario: 中文支持
- **WHEN** 图表包含中文标签或标题
- **THEN** 系统使用支持中文的字体（如 SimHei 或 Arial Unicode MS），避免乱码

#### Scenario: 网格和图例
- **WHEN** 生成图表
- **THEN** 启用 Y 轴网格线（虚线样式），图例位置为 upper right，标题使用 14pt 字体

#### Scenario: 保存为文件
- **WHEN** 用户指定输出路径
- **THEN** 图表保存为 PNG 格式，使用紧凑布局（bbox_inches='tight'）避免裁剪
