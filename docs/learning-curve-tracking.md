# Learning Curve Tracking Guide

## Overview

The Learning Curve Tracking feature allows you to monitor LLM performance over time by running evaluations on fixed benchmark suites and analyzing trends.

## Quick Start

### 1. Define a Benchmark Suite

Create a `benchmark.json` file with a fixed set of problems:

```json
{
  "name": "Standard Benchmark v1.0",
  "problems": [
    "leetcode_1",
    "leetcode_2",
    "leetcode_15",
    "leetcode_20",
    "leetcode_53"
  ],
  "frozen": true,
  "version": "1.0",
  "description": "Standard benchmark covering basic to medium difficulty"
}
```

### 2. Run Benchmark Evaluation

```bash
python -m src.main benchmark --suite benchmark.json
```

This will:
- Load the benchmark suite
- Run evaluation on all problems in the suite
- Save results to `results/benchmark/` with timestamp

### 3. Generate Learning Curve Report

After accumulating multiple evaluation results over time:

```bash
python -m src.main benchmark --suite benchmark.json --compare
```

This generates a comprehensive report with:
- Time series learning curves
- Model comparison charts
- Statistical analysis
- Performance growth metrics

## CLI Commands

### List Available Suites

```bash
python -m src.main benchmark --list-suites
```

### Run Benchmark

```bash
python -m src.main benchmark --suite <path-to-suite.json>
```

### Generate Comparison Report

```bash
python -m src.main benchmark --suite <suite.json> --compare --output <report-path>
```

## Benchmark Suite Format

A benchmark suite is a JSON file with the following structure:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Human-readable name |
| `problems` | array | Yes | List of problem IDs |
| `frozen` | boolean | No | Whether suite is immutable (default: true) |
| `version` | string | No | Version identifier (default: "1.0") |
| `description` | string | No | Optional description |

**Important:** Keep `frozen: true` to ensure historical comparisons remain valid.

## Results Storage

Results are automatically saved to `results/benchmark/` with the naming pattern:

```
{YYYYMMDD-HHMMSS}_{model-id}.json
```

Each result file contains:
- Timestamp
- Model ID
- Suite name
- Evaluation results per strategy
- Accuracy, tokens, cost metrics

## Analysis Features

### Learning Curves

Visualize performance over time for individual models:

```python
from src.benchmark import BenchmarkHistoryStorage
from src.benchmark.analysis import TrendAnalyzer

storage = BenchmarkHistoryStorage()
analyzer = TrendAnalyzer(storage)
analyzer.plot_learning_curve("gpt-4")
```

### Model Comparison

Compare multiple models on the same chart:

```python
analyzer.plot_model_comparison(model_ids=["gpt-4", "gpt-3.5-turbo"])
```

### Statistical Analysis

Calculate performance metrics:

```python
stats = analyzer.calculate_statistics("gpt-4")
print(f"Mean accuracy: {stats['mean_accuracy']:.2%}")
print(f"Growth rate: {stats['growth_rate']:.2%}")
```

## Best Practices

1. **Keep suites frozen:** Don't change problem sets to maintain valid comparisons
2. **Regular evaluations:** Run benchmarks weekly or monthly for meaningful trends
3. **Version tracking:** Record model versions in each evaluation
4. **Multiple suites:** Create different suites for different capability areas

## Scheduling Periodic Evaluations

Use system cron or task scheduler to run periodic evaluations:

```bash
# Example crontab entry for weekly evaluation
0 9 * * 1 cd /path/to/project && python -m src.main benchmark --suite benchmark.json
```

## Troubleshooting

### No data found for model

Ensure you have run at least one benchmark evaluation for the model.

### Missing problems in suite

Check that problem IDs in the suite match those in your dataset.

### Report generation fails

Verify matplotlib is installed: `pip install matplotlib`

## Examples

See `benchmark.example.json` for a sample benchmark suite configuration.

## API Reference

For programmatic access, see:
- `src/benchmark/suite.py` - Suite management
- `src/benchmark/history.py` - Results storage
- `src/benchmark/analysis.py` - Trend analysis
- `src/benchmark/report.py` - Report generation
