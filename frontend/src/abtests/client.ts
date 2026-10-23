import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  ABTestClient,
  ABTestJob,
  ABTestResults,
  ApiPage,
  CreatePayload,
  ListQuery,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('AB 测试接口响应格式不兼容', undefined, { field })
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

function configSubset(value: unknown, field: string) {
  const data = record(value, field)
  const model = record(data.model, `${field}.model`)
  const strategy = record(data.strategy, `${field}.strategy`)
  return {
    name: text(data.name, `${field}.name`, true),
    dataset_path: text(data.dataset_path, `${field}.dataset_path`),
    model: { model: text(model.model, `${field}.model.model`) },
    strategy: { name: text(strategy.name, `${field}.strategy.name`) },
    prompt_variants: array(
      data.prompt_variants,
      (value, field) => ({
        id: text(record(value, field).id, `${field}.id`),
      }),
      `${field}.prompt_variants`,
    ),
    seed: count(data.seed, `${field}.seed`),
    max_workers: count(data.max_workers, `${field}.max_workers`),
    api_key_id: text(data.api_key_id, `${field}.api_key_id`),
  }
}

function job(value: unknown, field = 'abtest'): ABTestJob {
  const data = record(value, field)
  return {
    id: text(data.id, `${field}.id`),
    name: text(data.name, `${field}.name`, true),
    status: text(data.status, `${field}.status`),
    config: configSubset(data.config, `${field}.config`),
    error_message: nullable(
      data.error_message,
      (value, field) => text(value, field, true),
      `${field}.error_message`,
    ),
    created_at: text(data.created_at, `${field}.created_at`),
    updated_at: text(data.updated_at, `${field}.updated_at`),
  }
}

function numberRecord(value: unknown, field: string): Record<string, number> {
  return Object.fromEntries(
    Object.entries(record(value, field)).map(([key, item]) => [
      key,
      number(item, `${field}.${key}`),
    ]),
  )
}
function signedNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) protocol(field)
  return value
}
function nullableSigned(value: unknown, field: string): number | null {
  return value === null ? null : signedNumber(value, field)
}
function ratePair(value: unknown, field: string) {
  const data = record(value, field)
  const ci95 = record(data.ci95, `${field}.ci95`)
  return {
    baseline: nullableNumber(data.baseline, `${field}.baseline`),
    treatment: nullableNumber(data.treatment, `${field}.treatment`),
    ci95: {
      difference: nullableSigned(ci95.difference, `${field}.ci95.difference`),
      lower: nullableSigned(ci95.lower, `${field}.ci95.lower`),
      upper: nullableSigned(ci95.upper, `${field}.ci95.upper`),
    },
  }
}

function results(value: unknown): ABTestResults {
  const data = record(value, 'results')
  const comparison = record(data.comparison, 'results.comparison')
  const statistics = record(
    comparison.statistics,
    'results.comparison.statistics',
  )
  return {
    name: text(data.name, 'results.name', true),
    generated_at: text(data.generated_at, 'results.generated_at'),
    variants: array(
      data.variants,
      (value, field) => {
        const row = record(value, field)
        return {
          id: text(row.id, `${field}.id`),
          description: text(row.description, `${field}.description`, true),
        }
      },
      'results.variants',
    ),
    baseline_id: nullable(data.baseline_id, text, 'results.baseline_id'),
    treatment_id: nullable(data.treatment_id, text, 'results.treatment_id'),
    comparison: {
      sample: ratePair(comparison.sample, 'results.comparison.sample'),
      formal: ratePair(comparison.formal, 'results.comparison.formal'),
      statistics: {
        categorical_test: text(
          statistics.categorical_test,
          'results.comparison.statistics.categorical_test',
        ),
        p_value: nullableNumber(
          statistics.p_value,
          'results.comparison.statistics.p_value',
        ),
        welch_t_p_value: nullableNumber(
          statistics.welch_t_p_value,
          'results.comparison.statistics.welch_t_p_value',
        ),
      },
      elapsed_seconds: numberRecord(
        comparison.elapsed_seconds,
        'results.comparison.elapsed_seconds',
      ),
      tokens: numberRecord(comparison.tokens, 'results.comparison.tokens'),
      failure_categories: Object.fromEntries(
        Object.entries(
          record(
            comparison.failure_categories,
            'results.comparison.failure_categories',
          ),
        ).map(([variant, categories]) => [
          variant,
          Object.fromEntries(
            Object.entries(
              record(
                categories,
                `results.comparison.failure_categories.${variant}`,
              ),
            ).map(([category, countValue]) => [
              category,
              count(countValue, `…failure_categories.${variant}.${category}`),
            ]),
          ),
        ]),
      ),
    },
  }
}

function pathId(id: string): string {
  if (!id.trim()) throw new ApiClientError('缺少资源 ID')
  return encodeURIComponent(id)
}
function listQuery(query: ListQuery): ListQuery {
  return {
    limit: query.limit,
    offset: query.offset,
    ...(query.status ? { status: query.status } : {}),
  }
}

// 注入 useAuthStore 提供的同一已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createABTestClient(http: AxiosInstance): ABTestClient {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    params?: unknown,
    signal?: AbortSignal,
    timeout = 10_000,
  ): Promise<T> {
    return read(
      await http.get<unknown, unknown>(url, { params, signal, timeout }),
    )
  }
  return {
    list: (query, signal) =>
      get(
        '/ab-tests',
        (value) => page(value, job, 'ab-tests'),
        listQuery(query),
        signal,
      ),
    get: async (id, signal) =>
      get(`/ab-tests/${pathId(id)}`, job, undefined, signal),
    create: async (payload: CreatePayload) =>
      job(
        await http.post<unknown, unknown>('/ab-tests', payload, {
          timeout: 20_000,
        }),
      ),
    remove: async (id) => {
      await http.delete(`/ab-tests/${pathId(id)}`, { timeout: 20_000 })
    },
    run: async (id) =>
      job(
        await http.post<unknown, unknown>(
          `/ab-tests/${pathId(id)}/run`,
          undefined,
          { timeout: 20_000 },
        ),
      ),
    results: async (id, signal) =>
      get(
        `/ab-tests/${pathId(id)}/results`,
        results,
        undefined,
        signal,
        20_000,
      ),
  }
}
