/** 基准 Suite 前端类型（issue #166 第②步）。字段与
 * api/services/benchmark_service.py 的 _suite_view/_run_view 及
 * api/experiment_models.py 的 BenchmarkSuiteCreateRequest/Update/RunRequest 对齐。
 */

export interface BenchmarkSuite {
  id: string
  name: string
  version: string
  description: string | null
  frozen: boolean
  problems: string[]
  created_at: string
  updated_at: string
}

export interface SuiteCreateInput {
  name: string
  problems: string[]
  version?: string
  description?: string
  frozen?: boolean
}

export interface SuiteUpdateInput {
  // 后端 BenchmarkSuiteUpdateRequest 无 name 字段，不支持重命名
  problems?: string[]
  version?: string
  description?: string | null
  frozen?: boolean
}

export interface BenchmarkRunRequestPayload {
  api_key_id: string
  dataset_path?: string | null
  dataset_id?: string
  model: string
  strategies?: { name: string }[]
  budget_cap_usd?: number
}

export interface BenchmarkRun {
  id: string
  suite_id: string
  task_id: string | null
  status: string
  model: string | null
  accuracy: number | null
  cost_usd: number | null
  error_message: string | null
  created_at: string
  updated_at: string
  results?: Record<string, unknown>
}

export type RunStatus =
  'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
export interface RunPage {
  items: BenchmarkRun[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface BenchmarkRunStarted extends BenchmarkRun {
  task_id: string
}

export interface LearningCurvePoint {
  run_id: string | null
  timestamp: string | null
  model: string
  accuracy: number | null
  cost_usd: number | null
}

export interface LearningCurve {
  suite_id: string
  suite_name: string
  data: LearningCurvePoint[]
  trends: {
    accuracy_growth_rate: number | null
    cost_growth_rate: number | null
  }
}

/** 任务快照（GET /tasks/{id} 的消费子集，形状同实验簇）。 */
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
}

export interface BenchmarkClient {
  runs(
    suiteId: string,
    query: { status?: RunStatus; limit: number; offset: number },
    signal?: AbortSignal,
  ): Promise<RunPage>
  suites(signal?: AbortSignal): Promise<BenchmarkSuite[]>
  getSuite(suiteId: string, signal?: AbortSignal): Promise<BenchmarkSuite>
  createSuite(input: SuiteCreateInput): Promise<BenchmarkSuite>
  updateSuite(suiteId: string, patch: SuiteUpdateInput): Promise<BenchmarkSuite>
  runSuite(
    suiteId: string,
    payload: BenchmarkRunRequestPayload,
  ): Promise<BenchmarkRunStarted>
  run(runId: string, signal?: AbortSignal): Promise<BenchmarkRun>
  learningCurve(suiteId: string, signal?: AbortSignal): Promise<LearningCurve>
  task(taskId: string, signal?: AbortSignal): Promise<TaskSnapshot>
}

/** Suite 创建/编辑草稿（problems 一行一个 ID 的文本态）。 */
export interface SuiteDraft {
  name: string
  version: string
  description: string
  frozen: boolean
  problems_text: string
}

export interface SuiteDraftErrors {
  name?: string
  version?: string
  problems_text?: string
}

/** Run 启动草稿。 */
export interface RunDraft {
  dataset_id?: string
  api_key_id: string
  dataset_path: string
  model: string
  strategies_text: string
  budget_cap_usd: string
}

export interface RunDraftErrors {
  api_key_id?: string
  dataset_path?: string
  model?: string
  budget_cap_usd?: string
}
