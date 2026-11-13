import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import { createPayload, readListQuery, writeListQuery } from './validation.ts'
import type {
  ApiPage,
  CreatePayload,
  Evaluation,
  EvaluationClient,
  EvaluationOptions,
  ExecutionProgress,
  FailureDiagnostic,
  ListQuery,
  ModelOptions,
  PageQuery,
  ProblemOption,
  ProblemResult,
  ProblemSource,
  ProgressInfo,
  ResultDetail,
  ResultSummary,
  StrategySummary,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('评估接口响应格式不兼容', undefined, { field })
}
function record(value: unknown, field: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    protocol(field)
  return value as Record<string, unknown>
}
function text(value: unknown, field: string, allowEmpty = false): string {
  if (typeof value !== 'string' || (!allowEmpty && !value.trim()))
    protocol(field)
  return value
}

export function failureDiagnostic(
  data: Record<string, unknown>,
  field: string,
): FailureDiagnostic {
  return {
    ...('error_stage' in data
      ? { error_stage: text(data.error_stage, `${field}.error_stage`) }
      : {}),
    ...('error_type' in data
      ? { error_type: text(data.error_type, `${field}.error_type`) }
      : {}),
  }
}
function boolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') protocol(field)
  return value
}
function number(value: unknown, field: string, max = Infinity): number {
  if (
    typeof value !== 'number' ||
    !Number.isFinite(value) ||
    value < 0 ||
    value > max
  )
    protocol(field)
  return value
}
function count(value: unknown, field: string): number {
  const result = number(value, field)
  if (!Number.isSafeInteger(result)) protocol(field)
  return result
}
function nullable<T>(
  value: unknown,
  read: (value: unknown, field: string) => T,
  field: string,
): T | null {
  return value === null ? null : read(value, field)
}
function array<T>(
  value: unknown,
  read: (value: unknown, field: string) => T,
  field: string,
): T[] {
  if (!Array.isArray(value)) protocol(field)
  return value.map((item, index) => read(item, `${field}.${index}`))
}
function source(value: unknown, field: string): ProblemSource {
  if (value !== 'shared' && value !== 'personal') protocol(field)
  return value
}
function page<T>(
  value: unknown,
  read: (value: unknown, field: string) => T,
  field: string,
): ApiPage<T> {
  const data = record(value, field)
  const limit = count(data.limit, `${field}.limit`)
  if (limit < 1 || limit > 100) protocol(`${field}.limit`)
  return {
    items: array(data.items, read, `${field}.items`),
    total: count(data.total, `${field}.total`),
    limit,
    offset: count(data.offset, `${field}.offset`),
    has_more: boolean(data.has_more, `${field}.has_more`),
  }
}
function progress(value: unknown, field: string): ProgressInfo {
  const data = record(value, field)
  return {
    current: count(data.current, `${field}.current`),
    total: count(data.total, `${field}.total`),
    message: nullable(
      data.message,
      (value, field) => text(value, field, true),
      `${field}.message`,
    ),
    ...('completed' in data
      ? { completed: nullable(data.completed, count, `${field}.completed`) }
      : {}),
    ...('percentage' in data
      ? {
          percentage: nullable(
            data.percentage,
            (value, field) => number(value, field, 100),
            `${field}.percentage`,
          ),
        }
      : {}),
  }
}
function executionProgress(value: unknown, field: string): ExecutionProgress {
  const data = record(value, field)
  return {
    completed_units: count(data.completed_units, `${field}.completed_units`),
    total_units: count(data.total_units, `${field}.total_units`),
    percentage: number(data.percentage, `${field}.percentage`, 100),
  }
}
function evaluation(value: unknown, field = 'evaluation'): Evaluation {
  const data = record(value, field)
  return {
    evaluation_id: text(data.evaluation_id, `${field}.evaluation_id`),
    created_at: text(data.created_at, `${field}.created_at`),
    updated_at: text(data.updated_at, `${field}.updated_at`),
    status: text(data.status, `${field}.status`),
    ...('async_task_id' in data
      ? {
          async_task_id: nullable(
            data.async_task_id,
            text,
            `${field}.async_task_id`,
          ),
        }
      : {}),
    ...Object.fromEntries(
      ['can_pause', 'can_resume', 'can_update', 'can_delete']
        .filter((key) => key in data)
        .map((key) => [key, boolean(data[key], `${field}.${key}`)]),
    ),
    can_start: boolean(data.can_start, `${field}.can_start`),
    can_cancel: boolean(data.can_cancel, `${field}.can_cancel`),
    execution_progress: executionProgress(
      data.execution_progress,
      `${field}.execution_progress`,
    ),
    strategy_names: array(data.strategy_names, text, `${field}.strategy_names`),
    model: nullable(data.model, text, `${field}.model`),
    ...('generation_timeout_seconds' in data
      ? {
          generation_timeout_seconds: count(
            data.generation_timeout_seconds,
            `${field}.generation_timeout_seconds`,
          ),
        }
      : {}),
    problem_count: count(data.problem_count, `${field}.problem_count`),
    spent_usd: number(data.spent_usd, `${field}.spent_usd`),
    ...('known_cost_usd' in data && {
      known_cost_usd: nullable(
        data.known_cost_usd,
        number,
        `${field}.known_cost_usd`,
      ),
    }),
    ...('unknown_cost_count' in data && {
      unknown_cost_count: count(
        data.unknown_cost_count,
        `${field}.unknown_cost_count`,
      ),
    }),
    ...('budget_status' in data && {
      budget_status: text(data.budget_status, `${field}.budget_status`),
    }),
    budget_cap_usd: nullable(
      data.budget_cap_usd,
      number,
      `${field}.budget_cap_usd`,
    ),
    error_message: nullable(
      data.error_message,
      (value, field) => text(value, field, true),
      `${field}.error_message`,
    ),
    progress: nullable(data.progress, progress, `${field}.progress`),
  }
}
function options(value: unknown): EvaluationOptions {
  const data = record(value, 'options')
  return {
    strategies: array(
      data.strategies,
      (value, field) => ({
        name: text(record(value, field).name, `${field}.name`),
      }),
      'options.strategies',
    ),
    sources: array(
      data.sources,
      (value, field) => {
        const row = record(value, field)
        return {
          id: source(row.id, `${field}.id`),
          label: text(row.label, `${field}.label`),
          problem_count: count(row.problem_count, `${field}.problem_count`),
        }
      },
      'options.sources',
    ),
  }
}
function problem(value: unknown, field: string): ProblemOption {
  const data = record(value, field)
  return {
    problem_id: text(data.problem_id, `${field}.problem_id`),
    title: text(data.title, `${field}.title`, true),
    difficulty: nullable(data.difficulty, text, `${field}.difficulty`),
    source: source(data.source, `${field}.source`),
  }
}
function recommendationWeakness(value: unknown, field: string) {
  const data = record(value, field)
  return {
    key: text(data.key, field + '.key'),
    failure_rate: number(data.failure_rate, field + '.failure_rate', 1),
    total: count(data.total, field + '.total'),
  }
}
function recommendedProblem(value: unknown, field: string) {
  const data = record(value, field)
  return {
    problem_id: text(data.problem_id, field + '.problem_id'),
    title: text(data.title, field + '.title', true),
    difficulty: nullable(data.difficulty, text, field + '.difficulty'),
    matching_groups: array(
      data.matching_groups,
      text,
      field + '.matching_groups',
    ),
    failure_rate: number(data.failure_rate, field + '.failure_rate', 1),
    total: count(data.total, field + '.total'),
  }
}
function recommendationPreview(value: unknown) {
  const data = record(value, 'recommendations')
  const reason = data.empty_reason
  if (
    reason !== null &&
    reason !== 'insufficient_history' &&
    reason !== 'no_weaknesses' &&
    reason !== 'no_candidates'
  )
    protocol('recommendations.empty_reason')
  return {
    weaknesses: array(data.weaknesses, recommendationWeakness, 'weaknesses'),
    problems: array(data.problems, recommendedProblem, 'recommended_problems'),
    empty_reason: reason,
  } as const
}
function recommendationSet(value: unknown, field = 'recommendation_set') {
  const data = record(value, field)
  return {
    id: text(data.id, field + '.id'),
    name: text(data.name, field + '.name'),
  }
}
function recommendationSetDetail(value: unknown) {
  const data = record(value, 'recommendation_set')
  return {
    ...recommendationSet(data),
    problems: array(data.problems, problem, 'recommendation_set.problems'),
    unavailable_count: count(
      data.unavailable_count,
      'recommendation_set.unavailable_count',
    ),
  }
}
function models(value: unknown): ModelOptions {
  const data = record(value, 'models')
  return {
    provider: text(data.provider, 'models.provider'),
    models: array(data.models, text, 'models.models'),
    complete: boolean(data.complete, 'models.complete'),
  }
}
function summary(value: unknown, field: string): ResultSummary {
  const data = record(value, field)
  return {
    id: text(data.id, `${field}.id`),
    run_id: nullable(data.run_id, text, `${field}.run_id`),
    status: text(data.status, `${field}.status`),
    model: nullable(data.model, text, `${field}.model`),
    strategy_names: array(data.strategy_names, text, `${field}.strategy_names`),
    created_at: text(data.created_at, `${field}.created_at`),
    completed_at: nullable(data.completed_at, text, `${field}.completed_at`),
  }
}
function strategy(value: unknown, field: string): StrategySummary {
  const data = record(value, field)
  const difficulties = record(data.by_difficulty, `${field}.by_difficulty`)
  return {
    name: text(data.name, `${field}.name`),
    success_rate: number(data.success_rate, `${field}.success_rate`, 1),
    total_problems: count(data.total_problems, `${field}.total_problems`),
    solved_problems: count(data.solved_problems, `${field}.solved_problems`),
    avg_tokens: number(data.avg_tokens, `${field}.avg_tokens`),
    estimated_cost_usd: number(
      data.estimated_cost_usd,
      `${field}.estimated_cost_usd`,
    ),
    unknown_cost_count: count(
      data.unknown_cost_count,
      `${field}.unknown_cost_count`,
    ),
    avg_execution_time: number(
      data.avg_execution_time,
      `${field}.avg_execution_time`,
    ),
    by_difficulty: Object.fromEntries(
      Object.entries(difficulties).map(([key, value]) => {
        const row = record(value, `${field}.by_difficulty.${key}`)
        return [
          key,
          {
            success_rate: number(
              row.success_rate,
              `${field}.by_difficulty.${key}.success_rate`,
              1,
            ),
            solved: count(row.solved, `${field}.by_difficulty.${key}.solved`),
            total: count(row.total, `${field}.by_difficulty.${key}.total`),
          },
        ]
      }),
    ),
  }
}
function problemResult(value: unknown, field: string): ProblemResult {
  const data = record(value, field)
  return {
    problem_id: text(data.problem_id, `${field}.problem_id`),
    strategy: text(data.strategy, `${field}.strategy`),
    status: text(data.status, `${field}.status`),
    ...failureDiagnostic(data, field),
    ...('error_message' in data
      ? {
          error_message: nullable(
            data.error_message,
            (value, field) => text(value, field, true),
            `${field}.error_message`,
          ),
        }
      : {}),
    iterations: nullable(data.iterations, number, `${field}.iterations`),
    tokens: nullable(data.tokens, number, `${field}.tokens`),
    execution_time: nullable(
      data.execution_time,
      number,
      `${field}.execution_time`,
    ),
  }
}
function detail(value: unknown): ResultDetail {
  const data = record(value, 'result')
  return {
    run_id: nullable(data.run_id, text, 'result.run_id'),
    status: text(data.status, 'result.status'),
    created_at: text(data.created_at, 'result.created_at'),
    completed_at: nullable(data.completed_at, text, 'result.completed_at'),
    strategies: array(data.strategies, strategy, 'result.strategies'),
    problems: page(data.problems, problemResult, 'result.problems'),
  }
}
function pathId(id: string): string {
  if (!id.trim()) throw new ApiClientError('缺少资源 ID')
  return encodeURIComponent(id)
}
function listQuery(query: ListQuery): ListQuery {
  return readListQuery(writeListQuery(query))
}
function pageQuery(query: PageQuery): PageQuery {
  const { limit, offset } = listQuery(query)
  return { limit, offset }
}
function payload(input: CreatePayload): CreatePayload {
  if (
    input.budget_cap_usd !== undefined &&
    (typeof input.budget_cap_usd !== 'number' ||
      !Number.isFinite(input.budget_cap_usd) ||
      input.budget_cap_usd < 0)
  )
    throw new ApiClientError('预算必须为有限非负数')
  return createPayload({
    ...input,
    budget_cap_usd:
      input.budget_cap_usd === undefined ? '' : String(input.budget_cap_usd),
  })
}

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createEvaluationClient(http: AxiosInstance) {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    params: unknown,
    signal?: AbortSignal,
    timeout = 10_000,
  ): Promise<T> {
    return read(
      await http.get<unknown, unknown>(url, { params, signal, timeout }),
    )
  }
  async function mutate(
    url: string,
    data?: CreatePayload,
  ): Promise<Evaluation> {
    return evaluation(
      await http.post<unknown, unknown>(url, data, { timeout: 20_000 }),
    )
  }
  async function post<T>(
    url: string,
    data: unknown,
    read: (value: unknown) => T,
    signal?: AbortSignal,
  ): Promise<T> {
    return read(
      await http.post<unknown, unknown>(url, data, { signal, timeout: 10_000 }),
    )
  }
  return {
    options: (signal) => get('/evaluation-options', options, undefined, signal),
    problems: (query, signal) =>
      get(
        '/evaluation-options/problems',
        (value) => page(value, problem, 'problems'),
        { ...pageQuery(query), source: query.source },
        signal,
      ),
    models: async (apiKeyId, signal) => {
      if (!apiKeyId.trim()) throw new ApiClientError('请选择可用密钥')
      return get(
        '/evaluation-options/models',
        models,
        { api_key_id: apiKeyId },
        signal,
        20_000,
      )
    },
    list: (query, signal) =>
      get(
        '/evaluations',
        (value) => page(value, evaluation, 'evaluations'),
        listQuery(query),
        signal,
      ),
    get: async (id, signal) =>
      get(`/evaluations/${pathId(id)}`, evaluation, undefined, signal),
    create: async (input) => {
      const { verify_problem_access, ...body } = payload(input)
      return mutate(
        body.dataset_version_id
          ? '/evaluations/with-dataset-version'
          : verify_problem_access
            ? '/evaluations/with-selection'
            : '/evaluations',
        body,
      )
    },
    start: async (id) => mutate(`/evaluations/${pathId(id)}/start`),
    cancel: async (id) => mutate(`/evaluations/${pathId(id)}/cancel`),
    pause: async (id, signal) => {
      await http.post(
        `/tasks/${pathId(id)}/pause`,
        {},
        { signal, timeout: 20_000 },
      )
    },
    resume: async (id, signal) => {
      await http.post(
        `/tasks/${pathId(id)}/resume`,
        {},
        { signal, timeout: 20_000 },
      )
    },
    update: async (id, input, signal) => {
      const budget = input.budget_cap_usd
      if (!Number.isFinite(budget) || budget < 0)
        throw new ApiClientError('预算须为非负有限数值')
      return evaluation(
        await http.patch(
          `/evaluations/${pathId(id)}`,
          { budget_cap_usd: budget },
          { signal, timeout: 20_000 },
        ),
      )
    },
    delete: async (id, signal) => {
      await http.delete(`/evaluations/${pathId(id)}`, {
        signal,
        timeout: 20_000,
      })
    },
    results: (query, signal) =>
      get(
        '/results',
        (value) => page(value, summary, 'results'),
        listQuery(query),
        signal,
      ),
    result: async (id, query, signal) =>
      get(`/results/${pathId(id)}`, detail, pageQuery(query), signal),
    selectedProblems: (ids: string[], signal: AbortSignal) =>
      post(
        '/evaluation-options/problems/selection',
        { problem_ids: ids },
        (value) => array(value, problem, 'selected_problems'),
        signal,
      ),
    previewRecommendations: (
      query: {
        run_ids: string[]
        source: 'all' | ProblemSource
        min_samples: number
      },
      signal: AbortSignal,
    ) =>
      post(
        '/results/recommendations/preview',
        query,
        recommendationPreview,
        signal,
      ),
    recommendationSets: (signal: AbortSignal) =>
      get(
        '/recommendation-sets',
        (value) => array(value, recommendationSet, 'recommendation_sets'),
        undefined,
        signal,
      ),
    recommendationSet: (id: string, signal: AbortSignal) =>
      get(
        `/recommendation-sets/${pathId(id)}`,
        recommendationSetDetail,
        undefined,
        signal,
      ),
    saveRecommendationSet: (name: string, ids: string[]) =>
      post(
        '/recommendation-sets',
        { name, problem_ids: ids },
        recommendationSet,
      ),
  } satisfies EvaluationClient & Record<string, unknown>
}
