/** 实验管理前端类型（issue #166 第①步）。
 *
 * 字段与 api/routes/experiments.py、api/experiment_models.py、
 * api/routes/tasks.py 的真实契约对齐；issue 原文假设的
 * cost_usd 预算、parallel_granularity、克隆等后端不存在，不建类型。
 */

export type ExperimentStatus =
  'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'

export interface ModelSpec {
  model: string
  base_url?: string
  temperature?: number
  api_key_id?: string
}

export interface StrategyConfig {
  name: string
  max_iterations?: number
  temperature?: number
  max_tokens?: number
  system_prompt?: string
}

export interface ProblemBudget {
  max_calls?: number
  max_tokens?: number
  max_seconds?: number
}

export interface ExperimentConfig {
  name: string
  dataset_path: string
  models: ModelSpec[]
  strategies: StrategyConfig[]
  repeats: number
  budget: ProblemBudget | null
  execution: 'serial' | 'parallel'
  max_workers: number
  api_key_id: string
}

export interface ExperimentJob {
  id: string
  name: string
  status: string
  config: ExperimentConfig
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface ExperimentJobWithTask extends ExperimentJob {
  task_id: string
}

export interface ApiPage<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface ListQuery {
  status?: string
  limit: number
  offset: number
}

export interface CreatePayload {
  name: string
  dataset_path: string
  models: ModelSpec[]
  strategies: StrategyConfig[]
  repeats: number
  budget: ProblemBudget | null
  execution: 'serial' | 'parallel'
  max_workers: number
  api_key_id: string
}

/** GET /tasks/{id} 的异步任务快照（ApiAsyncTaskResponse）。 */
export interface TaskSnapshot {
  id: string
  task_type: string
  entity_id: string
  status: string
  progress: {
    current: number
    total: number
    percentage: number
    current_step: string
  } | null
  error_message: string | null
  created_at: string
  updated_at: string
}

/** GET /experiments/{id}/comparison 中前端消费的子集（严格解析）。 */
export interface ComparisonReport {
  experiment: { experiment_id: string; name: string }
  combinations: CombinationRow[]
  model_comparison: {
    strategies: Record<
      string,
      { matrix: WinRateRow[]; significance: SignificanceRow[] }
    >
    cost_effectiveness: CostEffectivenessRow[]
  }
}

export interface CombinationRow {
  combo_id: string
  model: string
  strategy: string
  repeat: number
  denominator: { total: number; completed: number; budget_exhausted: number }
  solved: number
  pass_rate_over_total: number
  formal: { evaluable: number; solved: number; rate: number }
  cost: { total_cost_usd: number | null; known: boolean }
}

export interface WinRateRow {
  model: string
  solved: number
  against: Record<
    string,
    { wins: number; ties: number; losses: number; win_rate: number }
  >
}

export interface SignificanceRow {
  discordant_pairs: number
  p_value: number | null
  significant: boolean | null
  note: string
  a?: string
  b?: string
}

export interface CostEffectivenessRow {
  model: string
  solved: number
  total_cost_usd: number
  solved_per_usd: number
}

/** GET /experiments/{id}/panel 中前端消费的子集。 */
export interface PanelData {
  radar: { labels: string[]; datasets: { label: string; values: number[] }[] }
  scatter: { label: string; x: number; y: number }[]
  bar: {
    labels: string[]
    calls: number[]
    elapsed: number[]
    tokens: number[]
  }
  matrix_tables: {
    strategy: string
    rows: {
      model: string
      solved: number
      cells: { opponent: string; text: string }[]
    }[]
  }[]
  algorithm_radar: {
    labels: string[]
    datasets: { label: string; values: number[] }[]
  }
}

/** POST /pareto/analyze 响应中前端消费的子集。 */
export interface ParetoResult {
  accuracy_metric: string
  points: {
    id: string
    model: string
    strategy: string
    repeats: number
    mean_cost_usd: number
    mean_accuracy: number
    expected_solved_per_usd: number
    pareto_optimal: boolean
    dominated_by: string[]
  }[]
  frontier_ids: string[]
  best_value: { feasible: boolean; point_id: string; basis: string }
  budget_recommendations: {
    budget_usd: number
    feasible: boolean
    point_id: string
  }[]
}

export type OptimizeObjective =
  'highest_accuracy' | 'best_value' | 'lowest_cost'

/** POST /optimize 响应中前端消费的子集。 */
export interface OptimizeAdvisory {
  generated_at: string
  selected_objective: string
  ranking: {
    ranking: {
      model: string
      strategy: string
      accuracy: number | null
      cost_usd: number | null
      ratio: number | null
    }[]
    excluded: string[]
  }
  recommendations: Record<
    string,
    {
      objective: string
      feasible: boolean
      basis?: string
      note?: string
      model?: string
      strategy?: string
      accuracy?: number
      cost_usd?: number
      ratio?: number
    }
  >
  budget_plan?: { budget: number; feasible: boolean }
}

export interface ExperimentClient {
  list(query: ListQuery, signal?: AbortSignal): Promise<ApiPage<ExperimentJob>>
  get(experimentId: string, signal?: AbortSignal): Promise<ExperimentJob>
  create(payload: CreatePayload): Promise<ExperimentJob>
  remove(experimentId: string): Promise<void>
  run(experimentId: string): Promise<ExperimentJobWithTask>
  comparison(
    experimentId: string,
    signal?: AbortSignal,
  ): Promise<ComparisonReport>
  panel(experimentId: string, signal?: AbortSignal): Promise<PanelData>
  task(taskId: string, signal?: AbortSignal): Promise<TaskSnapshot>
  cancelTask(taskId: string): Promise<void>
  runningExperimentTasks(signal?: AbortSignal): Promise<TaskSnapshot[]>
  pareto(
    comparisons: unknown[],
    budgets: number[],
    accuracyMetric: 'overall' | 'formal',
    signal?: AbortSignal,
  ): Promise<ParetoResult>
  optimize(
    comparison: unknown,
    options: {
      budget?: number
      minAccuracy?: number
      objective?: OptimizeObjective
    },
    signal?: AbortSignal,
  ): Promise<OptimizeAdvisory>
}

/** 创建表单草稿（字符串态，提交前经 validation 归一）。 */
export interface ExperimentDraft {
  name: string
  dataset_path: string
  api_key_id: string
  models: { model: string; temperature: string; api_key_id: string }[]
  strategies: { name: string; max_iterations: string; temperature: string }[]
  repeats: string
  execution: 'serial' | 'parallel'
  max_workers: string
  budget_kind: 'none' | 'max_calls' | 'max_tokens' | 'max_seconds'
  budget_value: string
}

export interface DraftErrors {
  name?: string
  dataset_path?: string
  api_key_id?: string
  models?: string
  strategies?: string
  repeats?: string
  max_workers?: string
  budget_value?: string
}
