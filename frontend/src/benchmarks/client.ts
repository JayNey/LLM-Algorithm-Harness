import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  BenchmarkClient,
  BenchmarkRun,
  BenchmarkSuite,
  LearningCurve,
  TaskSnapshot,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('基准接口响应格式不兼容', undefined, { field })
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
function boolean(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') protocol(field)
  return value
}
function nullableNumber(value: unknown, field: string): number | null {
  return value === null ? null : number(value, field)
}
// 增长率可为负（准确率下滑/成本下降），不能走非负 number 校验。
function nullableSigned(value: unknown, field: string): number | null {
  if (value === null) return null
  if (typeof value !== 'number' || !Number.isFinite(value)) protocol(field)
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
function array<T>(
  value: unknown,
  read: (value: unknown, field: string) => T,
  field: string,
): T[] {
  if (!Array.isArray(value)) protocol(field)
  return value.map((item, index) => read(item, `${field}.${index}`))
}

function suite(value: unknown, field = 'suite'): BenchmarkSuite {
  const data = record(value, field)
  return {
    id: text(data.id, `${field}.id`),
    name: text(data.name, `${field}.name`),
    version: text(data.version, `${field}.version`),
    description: nullableText(data.description, `${field}.description`),
    frozen: boolean(data.frozen, `${field}.frozen`),
    problems: array(
      data.problems,
      (item, itemField) => text(item, itemField),
      `${field}.problems`,
    ),
    created_at: text(data.created_at, `${field}.created_at`),
    updated_at: text(data.updated_at, `${field}.updated_at`),
  }
}

function nullableText(value: unknown, field: string): string | null {
  return value === null || value === undefined ? null : text(value, field, true)
}

function run(value: unknown, field = 'run'): BenchmarkRun {
  const data = record(value, field)
  return {
    id: text(data.id, `${field}.id`),
    suite_id: text(data.suite_id, `${field}.suite_id`),
    status: text(data.status, `${field}.status`),
    model: nullableText(data.model, `${field}.model`),
    accuracy: nullableNumber(data.accuracy, `${field}.accuracy`),
    cost_usd: nullableNumber(data.cost_usd, `${field}.cost_usd`),
    error_message: nullableText(data.error_message, `${field}.error_message`),
    created_at: text(data.created_at, `${field}.created_at`),
    updated_at: text(data.updated_at, `${field}.updated_at`),
  }
}

function taskSnapshot(value: unknown, field = 'task'): TaskSnapshot {
  const data = record(value, field)
  const progress =
    data.progress === null || data.progress === undefined
      ? null
      : (() => {
          const raw = record(data.progress, `${field}.progress`)
          return {
            current: number(raw.current, `${field}.progress.current`),
            total: number(raw.total, `${field}.progress.total`),
            percentage: number(
              raw.percentage,
              `${field}.progress.percentage`,
              100,
            ),
            current_step: text(
              raw.current_step,
              `${field}.progress.current_step`,
              true,
            ),
          }
        })()
  return {
    id: text(data.id, `${field}.id`),
    entity_id: text(data.entity_id, `${field}.entity_id`),
    status: text(data.status, `${field}.status`),
    progress,
    error_message: nullableText(data.error_message, `${field}.error_message`),
  }
}

function learningCurve(value: unknown): LearningCurve {
  const data = record(value, 'learning-curve')
  const trends = record(data.trends, 'learning-curve.trends')
  return {
    suite_id: text(data.suite_id, 'learning-curve.suite_id'),
    suite_name: text(data.suite_name, 'learning-curve.suite_name', true),
    data: array(
      data.data,
      (value, field) => {
        const row = record(value, field)
        return {
          timestamp: nullableText(row.timestamp, `${field}.timestamp`),
          model: text(row.model, `${field}.model`),
          accuracy: nullableNumber(row.accuracy, `${field}.accuracy`),
          cost_usd: nullableNumber(row.cost_usd, `${field}.cost_usd`),
        }
      },
      'learning-curve.data',
    ),
    trends: {
      accuracy_growth_rate: nullableSigned(
        trends.accuracy_growth_rate,
        'learning-curve.trends.accuracy_growth_rate',
      ),
      cost_growth_rate: nullableSigned(
        trends.cost_growth_rate,
        'learning-curve.trends.cost_growth_rate',
      ),
    },
  }
}

function pathId(id: string): string {
  if (!id.trim()) throw new ApiClientError('缺少资源 ID')
  return encodeURIComponent(id)
}

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createBenchmarkClient(http: AxiosInstance): BenchmarkClient {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    signal?: AbortSignal,
    timeout = 10_000,
  ): Promise<T> {
    return read(await http.get<unknown, unknown>(url, { signal, timeout }))
  }
  return {
    suites: async (signal) =>
      get(
        '/benchmarks/suites',
        (value) => {
          // 后端不分页：全量 items 壳（PaginatedData）
          const data = record(value, 'suites')
          return array(data.items, suite, 'suites.items')
        },
        signal,
      ),
    getSuite: async (id, signal) =>
      get(`/benchmarks/suites/${pathId(id)}`, suite, signal),
    createSuite: async (input) =>
      suite(
        await http.post<unknown, unknown>('/benchmarks/suites', input, {
          timeout: 20_000,
        }),
      ),
    updateSuite: async (id, patch) =>
      suite(
        await http.patch<unknown, unknown>(
          `/benchmarks/suites/${pathId(id)}`,
          patch,
          {
            timeout: 20_000,
          },
        ),
      ),
    runSuite: async (id, payload) => {
      const data = await http.post<unknown, unknown>(
        `/benchmarks/suites/${pathId(id)}/run`,
        payload,
        { timeout: 20_000 },
      )
      const row = record(data, 'run')
      return { ...run(row, 'run'), task_id: text(row.task_id, 'run.task_id') }
    },
    run: async (runId, signal) =>
      get(`/benchmarks/runs/${pathId(runId)}`, run, signal, 20_000),
    learningCurve: async (id, signal) =>
      get(
        `/benchmarks/learning-curve/${pathId(id)}`,
        learningCurve,
        signal,
        20_000,
      ),
    task: async (taskId, signal) =>
      get(`/tasks/${pathId(taskId)}`, taskSnapshot, signal),
  }
}
