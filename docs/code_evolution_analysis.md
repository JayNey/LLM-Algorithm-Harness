# Code Evolution Analysis

## Overview

The Code Evolution Analysis module tracks and analyzes how code quality metrics change across iterations in multi-round strategies. It helps identify quality regressions and understand why code quality might decline during iterative refinement.

## Features

- **Quality Drop Detection**: Automatically detects significant drops in quality metrics across iterations
- **Root Cause Analysis**: Applies rule-based heuristics to explain why quality drops occurred
- **Visualization**: Generates charts showing quality evolution over time
- **Reporting**: Produces markdown reports summarizing quality trends and issues

## Architecture

### Core Components

1. **EvolutionAnalyzer** (`src/analysis/evolution.py`)
   - Main class for analyzing quality evolution
   - Methods:
     - `identify_quality_drops()`: Detect significant quality regressions
     - `analyze_drop_reason()`: Determine why a drop occurred
     - `generate_evolution_chart()`: Create PNG visualization
     - `generate_evolution_report()`: Generate markdown report

2. **Evolution Report Generator** (`src/reporting/evolution_report.py`)
   - Integration with experiment reporting system
   - Functions:
     - `generate_evolution_section()`: Create markdown section for reports
     - `should_include_evolution_analysis()`: Check if analysis is applicable

3. **Strategy Integration** (`src/strategies/multi_round_feedback.py`)
   - Automatic detection and logging of quality drops during execution
   - Non-blocking: analysis failures don't affect strategy execution

## Usage

### Basic Analysis

```python
from src.analysis.evolution import EvolutionAnalyzer
from src.models import ExecutionResult

# After running a multi-round strategy
result: ExecutionResult = strategy.execute(problem)

# Analyze evolution
analyzer = EvolutionAnalyzer(result)
drops = analyzer.identify_quality_drops()

# Generate report
report_text = analyzer.generate_evolution_report()
print(report_text)

# Generate chart
from pathlib import Path
analyzer.generate_evolution_chart(Path("evolution.png"))
```

### Configuration

Evolution analysis is controlled by the presence of quality data in iterations. To enable it:

1. Enable quality analysis in your harness configuration:
```yaml
enable_quality_analysis: true
```

2. Evolution analysis will automatically run for multi-round strategies when quality data is present

### Integration with Reports

Evolution analysis is automatically included in experiment reports when applicable:

```python
from src.reporting.evolution_report import generate_evolution_section

# In your report generation code
evolution_section = generate_evolution_section(result, output_dir=report_dir)
if evolution_section:
    report += evolution_section
```

## Quality Drop Detection

### Thresholds

- **Overall Score**: Absolute drop of ≥10 points (0-100 scale)
- **Individual Metrics**: Relative drop of ≥15%

### Detected Metrics

- Overall quality score
- Time complexity performance score
- Space complexity memory efficiency score
- Readability score
- Style consistency score

### Example

```python
# Iteration 1: overall_score = 85.0
# Iteration 2: overall_score = 65.0
# Drop detected: 20 points (>10 threshold)
```

## Drop Reason Analysis

The analyzer applies rule-based heuristics to explain quality drops:

### 1. Syntax Errors
Detected when:
- Overall score drops below 30
- Readability score drops significantly

Indicates: Code became syntactically invalid or severely malformed

### 2. Over-Optimization
Detected when:
- Time complexity improves OR space complexity improves
- But readability drops significantly

Indicates: Code was optimized at the expense of readability

### 3. Code Bloat
Detected when:
- Readability drops
- Style score drops

Indicates: Code became more complex or verbose

### 4. Style Degradation
Detected when:
- Style score drops
- Other metrics relatively stable

Indicates: Code formatting or style conventions violated

### 5. Generic Regression
Default when no specific pattern matches

## Chart Visualization

The evolution chart includes:

1. **Top Panel**: Overall quality score trend
2. **Bottom Panel**: Individual metric trends
   - Time complexity (squares)
   - Space complexity (triangles)
   - Readability (diamonds)
   - Style consistency (inverted triangles)

All scores plotted on 0-100 scale for easy comparison.

## Report Format

### Example Report

```markdown
## Code Quality Evolution Analysis

### Summary

- Total iterations: 3
- Iterations with quality data: 3
- Initial overall score: 70.0
- Final overall score: 75.0
- Net change: +5.0 (improvement)

### Quality Drops Detected

Found 1 quality drop(s):

**Iteration 2:**

- Readability: 80.0 → 60.0
  - Reason: Code was over-optimized for performance at the expense of readability

### Iteration Details

**Iteration 1:**
- Overall Score: 70.0
- Time Complexity: 75.0
- Readability: 80.0

**Iteration 2:**
- Overall Score: 72.0
- Time Complexity: 85.0
- Readability: 60.0

**Iteration 3:**
- Overall Score: 75.0
- Time Complexity: 85.0
- Readability: 65.0
```

## Logging

During multi-round strategy execution, quality drops are logged:

```python
# Warning log when drops detected
logger.warning(
    "quality_drops_detected",
    problem_id="problem_123",
    num_drops=2,
    affected_iterations=[2, 3]
)

# Info log for each drop detail
logger.info(
    "quality_drop_detail",
    iteration=2,
    metric="readability_score",
    previous_value=80.0,
    current_value=60.0,
    reason="Code was over-optimized..."
)
```

## Error Handling

Evolution analysis is designed to be non-blocking:

- Analysis failures are caught and logged as errors
- Strategy execution continues normally
- Missing quality data is handled gracefully
- Chart generation failures don't prevent report generation

## Testing

### Unit Tests

Located in `tests/test_evolution_analyzer.py`:
- Drop detection logic
- Reason analysis heuristics
- Chart generation
- Report generation

### Integration Tests

Located in `tests/strategies/test_multi_round_quality_analysis.py`:
- Strategy integration
- Logging behavior
- Configuration handling

Located in `tests/reporting/test_evolution_report.py`:
- Report section generation
- Chart output
- Edge cases

Run all tests:
```bash
pytest tests/test_evolution_analyzer.py \
       tests/strategies/test_multi_round_quality_analysis.py \
       tests/reporting/test_evolution_report.py -v
```

## Extending the System

### Adding New Drop Patterns

To add a new drop reason pattern, edit `analyze_drop_reason()` in `src/analysis/evolution.py`:

```python
# Check for your pattern
if (condition1 and condition2):
    return "Your explanation of what happened"
```

### Adding New Metrics

To track additional quality metrics:

1. Ensure the metric is included in `CodeQualityMetrics` model
2. Add extraction logic in `identify_quality_drops()`
3. Update chart generation to include the new metric
4. Update report generation to display the new metric

### Custom Thresholds

Modify thresholds in `identify_quality_drops()`:

```python
# Current thresholds
RELATIVE_THRESHOLD = 0.15  # 15% relative drop
OVERALL_ABSOLUTE_THRESHOLD = 10  # 10 points absolute drop

# Adjust as needed for your use case
```

## Performance Considerations

- Analysis runs only when quality data is present
- Chart generation is optional and can be skipped
- Analysis is performed per-problem after execution completes
- No impact on strategy execution performance

## Limitations

- Requires at least 2 iterations with quality data
- Heuristics are rule-based, not ML-based
- Chart generation requires matplotlib
- Analysis is post-hoc, not real-time during iteration

## Future Enhancements

Potential improvements:
- Machine learning-based drop reason classification
- Real-time quality monitoring during iteration
- Automated suggestions for fixing quality issues
- Comparative analysis across different strategies
- Trend prediction for future iterations
