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

### HTTP run history

Authenticated API runs are stored in the business database, separately from CLI
JSON history. Send `Authorization: Bearer <access_token>` to:

```http
GET /api/v1/benchmarks/suites/{suite_id}/runs?status=running&limit=20&offset=0
```

`status` is optional and accepts exactly one of `pending`, `running`, `paused`,
`completed`, `failed`, or `cancelled`. Omit it to include all statuses. Filtering
happens before pagination and counting. `limit` defaults to 20 and must be 1–100;
`offset` defaults to 0 and must be nonnegative. Invalid parameters return the
standard 400 validation error response.

Runs are ordered by `created_at DESC, id DESC`, including an ID tie-breaker when
timestamps match. This gives stable pages for unchanged data; concurrent inserts
can shift offset-based page boundaries.

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "run-id",
        "suite_id": "suite-id",
        "task_id": "task-id",
        "status": "running",
        "model": "gpt-test",
        "dataset_snapshot": null,
        "accuracy": null,
        "cost_usd": null,
        "error_message": null,
        "created_at": "2026-10-28T12:00:00Z",
        "updated_at": "2026-10-28T12:01:00Z",
        "started_at": "2026-10-28T12:01:00Z",
        "completed_at": null
      }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0,
    "has_more": false
  },
  "message": "Benchmark runs retrieved successfully"
}
```

`total` counts all matching owned runs, independent of the requested page.
`has_more` is true when `offset + limit < total`. Empty suites return a valid
empty page with `total: 0`; an offset beyond the end also returns `items: []`.
Unavailable metrics, lifecycle timestamps, dataset summaries and task associations
remain `null`; a measured zero remains `0`.

Use an item's `id` with `GET /api/v1/benchmarks/runs/{run_id}` to retrieve results.
The detail response retains existing fields and also includes `task_id`,
`started_at` and `completed_at`. When `task_id` is non-null, use
`GET /api/v1/tasks/{task_id}` for progress. An association must match the run ID,
the current owner and task type `benchmark`; if multiple records exist, the newest
by `created_at DESC, id DESC` is returned. Missing associations remain `null`.
Suite, run and task ownership are checked independently. Foreign runs are excluded
even if they reference an owned suite; missing or foreign suite/run resources
return 404, and unauthenticated requests return 401.

### HTTP learning curve

`GET /api/v1/benchmarks/learning-curve/{suite_id}` retains its `suite_id`,
`suite_name`, `data` and `trends` shape. Each point now also contains `run_id`,
matching the history item's `id` and the existing detail route. Existing
`timestamp`, `model`, `accuracy` and `cost_usd` fields and trend calculations are
unchanged. Only the current user's `completed` runs contribute, ordered by
`completed_at, id` ascending; active, failed, cancelled and foreign runs do not
affect the curve. A suite without completed runs returns `data: []` and null
growth rates. Clients can ignore the additive `run_id` field.

### Python modules

For programmatic access, see:
- `src/benchmark/suite.py` - Suite management
- `src/benchmark/history.py` - Results storage
- `src/benchmark/analysis.py` - Trend analysis
- `src/benchmark/report.py` - Report generation
