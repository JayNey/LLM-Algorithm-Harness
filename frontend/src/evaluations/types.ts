export interface ApiPage<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}
export interface PageQuery {
  limit: number
  offset: number
}
export interface ListQuery extends PageQuery {
  status?: string
}
export type ProblemSource = 'shared' | 'personal'
export interface ProblemQuery extends PageQuery {
  source: 'all' | ProblemSource
}
export interface ExecutionProgress {
  completed_units: number
  total_units: number
  percentage: number
}
export interface ProgressInfo {
  current: number
  total: number
  message: string | null
  completed?: number | null
  percentage?: number | null
}
export interface Evaluation {
  evaluation_id: string
  created_at: string
  updated_at: string
  status: string
  can_start: boolean
  can_cancel: boolean
  execution_progress: ExecutionProgress
  strategy_names: string[]
  model: string | null
  problem_count: number
  spent_usd: number
  budget_cap_usd: number | null
  error_message: string | null
  progress: ProgressInfo | null
}
export interface EvaluationOptions {
  strategies: { name: string }[]
  sources: { id: ProblemSource; label: string; problem_count: number }[]
}
export interface ModelOptions {
  provider: string
  models: string[]
  complete: boolean
}
export interface ProblemOption {
  problem_id: string
  title: string
  difficulty: string | null
  source: ProblemSource
}
export interface ResultSummary {
  id: string
  run_id: string | null
  status: string
  model: string | null
  strategy_names: string[]
  created_at: string
  completed_at: string | null
}
export interface StrategySummary {
  name: string
  success_rate: number
  total_problems: number
  solved_problems: number
  avg_tokens: number
  estimated_cost_usd: number
  unknown_cost_count: number
  avg_execution_time: number
  by_difficulty: Record<
    string,
    { success_rate: number; solved: number; total: number }
  >
}
export interface ProblemResult {
  problem_id: string
  strategy: string
  status: string
  iterations: number | null
  tokens: number | null
  execution_time: number | null
}
export interface ResultDetail {
  run_id: string | null
  status: string
  created_at: string
  completed_at: string | null
  strategies: StrategySummary[]
  problems: ApiPage<ProblemResult>
}
/** HTTP task truth with optional result data from the same observation cycle. */
export interface EvaluationSnapshot extends Evaluation {
  result?: ResultDetail | null
  resultError?: string | null
}
export interface CreatePayload {
  api_key_id: string
  model: string
  problem_ids: string[]
  strategy_names: string[]
  budget_cap_usd?: number
}
export interface Draft {
  api_key_id: string
  model: string
  problem_ids: string[]
  strategy_names: string[]
  budget_cap_usd: string
}
// 包含当前来源已核实的跨页可选 ID；调用方不应仅传当前页。
export interface DraftAvailable {
  api_key_ids: readonly string[]
  models: readonly string[]
  problem_ids: readonly string[]
  strategy_names: readonly string[]
}
export type DraftErrors = Partial<Record<keyof Draft, string>>
export interface ResultAvailability {
  kind:
    | 'waiting'
    | 'partial'
    | 'paused'
    | 'failed'
    | 'cancelled'
    | 'complete'
    | 'incomplete'
    | 'empty'
    | 'unknown'
  recorded_units: number | null
  expected_units: number
}
export interface EvaluationClient {
  options(signal?: AbortSignal): Promise<EvaluationOptions>
  problems(
    query: ProblemQuery,
    signal?: AbortSignal,
  ): Promise<ApiPage<ProblemOption>>
  models(apiKeyId: string, signal?: AbortSignal): Promise<ModelOptions>
  list(query: ListQuery, signal?: AbortSignal): Promise<ApiPage<Evaluation>>
  get(evaluationId: string, signal?: AbortSignal): Promise<Evaluation>
  create(payload: CreatePayload): Promise<Evaluation>
  start(evaluationId: string): Promise<Evaluation>
  cancel(evaluationId: string): Promise<Evaluation>
  results(
    query: ListQuery,
    signal?: AbortSignal,
  ): Promise<ApiPage<ResultSummary>>
  result(
    evaluationId: string,
    page: PageQuery,
    signal?: AbortSignal,
  ): Promise<ResultDetail>
}
