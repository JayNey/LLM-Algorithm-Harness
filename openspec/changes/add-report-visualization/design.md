## Context

当前项目已实现核心评测框架（`harness.py`、`strategies/`、`sandbox_executor.py`），输出格式仅限于 JSON 文件和终端文本。文档中设计了 `MetricsCalculator` 和 `ReportGenerator` 模块，但未实现。

现有架构约束：
- 不修改核心评测逻辑（`harness.py`、`models.py`、`strategies/`）
- 已有依赖：`pydantic`、`structlog`、数据模型完整定义在 `models.py`
- 输出目录由 `HarnessConfig.output_dir` 控制，默认 `./results`

## Goals / Non-Goals

**Goals:**
- 提供 4 种独立的报告生成模块，可单独或组合使用
- 保持与现有 JSON 输出的向后兼容
- 生成高质量、可重复的可视化图表
- 提供完整的单元测试覆盖

**Non-Goals:**
- 不实现实时报告（仍是评测完成后生成）
- 不实现交互式 Web Dashboard（HTML 报告是静态的）
- 不支持自定义图表主题或模板（使用固定样式）
- 不修改现有 `StrategyReport` 数据模型

## Decisions

### Decision 1: 独立模块架构

**选择**：创建 `src/reporting/` 包，包含 4 个独立模块  
**理由**：
- 松耦合：每个模块可独立测试和使用
- 渐进式集成：可逐步添加到 `main.py`，不影响现有流程
- 可扩展：未来添加新报告格式（如 PDF）无需修改现有代码

**替代方案**：
- 方案 A：在 `harness.py` 中直接添加报告方法 → 被拒绝：违反单一职责原则，难以测试
- 方案 B：创建单一 `ReportGenerator` 类 → 被拒绝：类过于庞大，职责不清晰

### Decision 2: 使用 pandas 处理 CSV 导出

**选择**：使用 `pandas.DataFrame.to_csv()`  
**理由**：
- 自动处理 UTF-8 BOM、字段转义、特殊字符
- 成熟稳定，减少手写 CSV 的边界情况 bug
- 与数据分析工作流集成良好

**替代方案**：
- 方案 A：使用标准库 `csv.writer` → 被拒绝：需要手动处理编码和转义，代码更复杂
- 方案 B：手写 CSV 字符串拼接 → 被拒绝：不安全，容易出现格式错误

### Decision 3: matplotlib 图表保存为内存 BytesIO

**选择**：图表先保存到 `BytesIO`，再编码为 Base64 或写入文件  
**理由**：
- 避免临时文件管理和清理
- HTML 生成器可直接获取 Base64 字符串
- 测试时无需文件系统 mock

**实现**：
```python
import io
import base64

buf = io.BytesIO()
fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
buf.seek(0)
base64_str = base64.b64encode(buf.read()).decode('utf-8')
```

### Decision 4: 中文字体回退策略

**选择**：使用字体回退列表，优雅降级  
**理由**：
- 跨平台兼容：不同操作系统有不同字体
- 避免硬依赖：缺少字体时仍能生成图表（英文标签）

**实现**：
```python
# 按优先级尝试
fonts = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
for font in fonts:
    if font in matplotlib.font_manager.findSystemFonts():
        plt.rcParams['font.sans-serif'] = [font]
        break
```

### Decision 5: HTML 报告使用简单 JavaScript

**选择**：内嵌 < 100 行原生 JavaScript 实现表格排序  
**理由**：
- 自包含：无外部库依赖
- 轻量：不需要 React/Vue 等框架
- 离线可用：无 CDN 依赖

**替代方案**：
- 方案 A：引入 jQuery → 被拒绝：为简单功能引入重量级库
- 方案 B：使用 DataTables.js → 被拒绝：增加复杂度，学习曲线陡峭

### Decision 6: 报告生成接口设计

**选择**：每个生成器提供独立的静态方法或类方法  
**接口示例**：
```python
# CSV Exporter
CSVExporter.export(results: List[ExecutionResult], output_path: str)
CSVExporter.export_all(results_dict: Dict[str, List[ExecutionResult]], output_path: str)

# Markdown Generator
MarkdownGenerator.generate(metrics: Dict[str, StrategyMetrics], 
                          results: Dict[str, List[ExecutionResult]],
                          output_path: str) -> str

# Chart Generator
ChartGenerator.generate_success_rate_chart(metrics: Dict[str, StrategyMetrics]) -> BytesIO
ChartGenerator.generate_token_chart(metrics: Dict[str, StrategyMetrics]) -> BytesIO
ChartGenerator.generate_iteration_distribution(results: Dict[str, List[ExecutionResult]]) -> BytesIO

# HTML Generator
HTMLGenerator.generate(metrics: Dict[str, StrategyMetrics],
                      results: Dict[str, List[ExecutionResult]],
                      output_path: str,
                      include_charts: bool = True) -> str
```

**理由**：
- 无状态：生成器不保存状态，避免线程安全问题
- 清晰接口：输入输出明确，易于理解和测试
- 组合灵活：用户可选择性调用

## Risks / Trade-offs

### Risk 1: matplotlib 中文字体缺失
**表现**：图表中文标签显示为方框  
**缓解**：
1. 提供字体安装文档
2. 代码中检测字体可用性，缺失时显示警告
3. 回退到英文标签

### Risk 2: 大规模结果集的内存占用
**表现**：1000+ 问题评测时生成报告可能消耗大量内存（pandas DataFrame + matplotlib）  
**缓解**：
1. CSV 导出使用流式写入（pandas `chunksize` 参数）
2. 图表生成后立即释放 matplotlib figure 对象：`plt.close(fig)`
3. 文档中建议按策略分批生成报告

### Risk 3: HTML 报告体积过大
**表现**：Base64 编码的图片导致 HTML 文件 > 5MB  
**缓解**：
1. 控制图表 DPI（100 而非 300）
2. 图表压缩（PNG 优化）
3. 提供 `include_charts=False` 选项，仅嵌入图表链接

### Risk 4: 跨平台路径问题
**表现**：Windows 上路径分隔符不一致  
**缓解**：
1. 统一使用 `pathlib.Path`
2. 输出路径始终转换为绝对路径
3. 测试覆盖 Windows/macOS/Linux

## Open Questions

暂无：所有关键设计决策已确定，实现细节可在开发过程中调整。
