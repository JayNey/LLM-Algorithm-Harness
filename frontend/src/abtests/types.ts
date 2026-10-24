/** A/B 测试前端类型（issue #166 第②步）。
 * 字段与 api/services/ab_test_service.py 的 _job_view、
 * api/experiment_models.py 的 ABTestCreateRequest、src/ab_testing.py 的
 * 结果报告对齐。AB 为进程内线程执行：无 task_id、无进度，只能轮询状态。
 */

export interface ABTestJob {
  id: string
  name: string
  status: string
  config: ABTestConfig
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface ABTestConfig {
  name: string
  dataset_path: string
  model: { model: string; temperature?: number }
  strategy: { name: string; max_iterations?: number; temperature?: number }
  prompt_variants: { id: string; description?: string }[]
  seed: number
  max_workers: number
  api_key_id: string
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
  model: { model: string; temperature?: number }
  strategy: { name: string; max_iterations?: number; temperature?: number }
  prompt_variants: {
    id: string
    description?: string
    system_prompt?: string
    prefix?: string
    suffix?: string
  }[]
  seed: number
  max_workers: number
  api_key_id: string
}

/** GET /ab-tests/{id}/results 中前端消费的子集（严格解析）。 */
export interface ABTestResults {
  name: string
  generated_at: string
  variants: { id: string; description: string }[]
  baseline_id: string | null
  treatment_id: string | null
  comparison: {
    sample: RatePair
    formal: RatePair
    statistics: {
      categorical_test: string
      p_value: number | null
      welch_t_p_value: number | null
    }
    /** 按变体分组的总耗时（秒） */
    elapsed_seconds: Record<string, number>
    /** 按变体分组的总 token 数 */
    tokens: Record<string, number>
    /** 按变体分组的失败分类计数 */
    failure_categories: Record<string, Record<string, number>>
  }
}

export interface RatePair {
  baseline: number | null
  treatment: number | null
  ci95: {
    difference: number | null
    lower: number | null
    upper: number | null
  }
}

export interface ABTestClient {
  list(query: ListQuery, signal?: AbortSignal): Promise<ApiPage<ABTestJob>>
  get(testId: string, signal?: AbortSignal): Promise<ABTestJob>
  create(payload: CreatePayload): Promise<ABTestJob>
  remove(testId: string): Promise<void>
  run(testId: string): Promise<ABTestJob>
  results(testId: string, signal?: AbortSignal): Promise<ABTestResults>
}

export interface PromptVariantDraft {
  id: string
  description: string
  system_prompt: string
  prefix: string
  suffix: string
}

export interface ABTestDraft {
  name: string
  dataset_path: string
  api_key_id: string
  model: string
  model_temperature: string
  strategy: string
  strategy_max_iterations: string
  seed: string
  max_workers: string
  variants: PromptVariantDraft[]
}

export interface DraftErrors {
  name?: string
  dataset_path?: string
  api_key_id?: string
  model?: string
  strategy?: string
  seed?: string
  max_workers?: string
  variants?: string
}
