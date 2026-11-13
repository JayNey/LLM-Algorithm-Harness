import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import { failureDiagnostic } from './client.ts'
import type { FailureDiagnostic, StrategySummary } from './types.ts'

/** 单次运行以结果的 run_id 为准；全账号由后端限定为已完成运行。 */
export type AnalyticsScope =
  { kind: 'run'; runId: string } | { kind: 'account' }
/** 只对基础统计、四类图表与按标签失败率生效；后端按单值精确匹配。 */
export interface AnalyticsFilters {
  strategy?: string
  difficulty?: string
  tag?: string
}
export interface RateBucket {
  success_rate: number
  solved: number
  total: number
}
export interface SuccessRateStats extends RateBucket {
  avg_execution_time: number
  by_difficulty: Record<string, RateBucket>
  by_tag: Record<string, RateBucket>
}
export interface TokenStats {
  total_tokens: number
  avg_tokens: number
  estimated_cost_usd: number
  unknown_cost_count: number
}
export interface IterationStats {
  known_count: number
  unknown_count: number
  average: number | null
  distribution: { iterations: number; count: number }[]
}
export type FailureModeCounts = Record<string, number>
export interface SuccessRateChart {
  points: { name: string; success_rate: number }[]
}
export interface TokenChart {
  series: {
    name: string
    points: { problem_id: string; tokens: number | null }[]
  }[]
}
export interface CostAccuracyChart {
  points: { name: string; success_rate: number; estimated_cost_usd: number }[]
}
export interface CapabilityRadar {
  dimensions: string[]
  series: { name: string | null; data: number[] }[]
  problem_counts: Record<string, number>
}
export interface FailuresByTag {
  tags: Record<string, RateBucket>
}
export interface FailureSummary {
  modes: Record<string, number>
  categories: Record<string, number>
  clusters: (FailureDiagnostic & { pattern: string; count: number })[]
}
export interface FailureCase extends FailureDiagnostic {
  problem_id: string
  strategy: string
  status: string
  error_message: string | null
}
export interface FailureCases {
  items: FailureCase[]
}
export interface StrategyComparison {
  strategies: StrategySummary[]
}
export interface ModelComparison {
  models: { model: string | null; strategies: StrategySummary[] }[]
}
export interface HistoryComparison {
  series: {
    run_id: string | null
    completed_at: string | null
    strategies: StrategySummary[]
  }[]
}
export interface AnalyticsClient {
  successRate(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<SuccessRateStats>
  tokens(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<TokenStats>
  iterations(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<IterationStats>
  failureModes(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<FailureModeCounts>
  successRateChart(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<SuccessRateChart>
  tokenChart(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<TokenChart>
  costAccuracy(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<CostAccuracyChart>
  capabilityRadar(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<CapabilityRadar>
  failuresByTag(
    scope: AnalyticsScope,
    filters: AnalyticsFilters,
    signal?: AbortSignal,
  ): Promise<FailuresByTag>
  failureSummary(runId: string, signal?: AbortSignal): Promise<FailureSummary>
  failureCases(runId: string, signal?: AbortSignal): Promise<FailureCases>
  compareStrategies(
    runId: string,
    signal?: AbortSignal,
  ): Promise<StrategyComparison>
  compareModels(signal?: AbortSignal): Promise<ModelComparison>
  compareHistory(
    runId: string,
    signal?: AbortSignal,
  ): Promise<HistoryComparison>
}

function protocol(field: string): never {
  throw new ApiClientError('结果分析接口响应格式不兼容', undefined, { field })
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
function mapping<T>(
  value: unknown,
  read: (value: unknown, field: string) => T,
  field: string,
): Record<string, T> {
  return Object.fromEntries(
    Object.entries(record(value, field)).map(([key, item]) => [
      key,
      read(item, `${field}.${key}`),
    ]),
  )
}
function bucket(value: unknown, field: string): RateBucket {
  const data = record(value, field)
  return {
    success_rate: number(data.success_rate, `${field}.success_rate`, 1),
    solved: count(data.solved, `${field}.solved`),
    total: count(data.total, `${field}.total`),
  }
}
function strategy(value: unknown, field: string): StrategySummary {
  const data = record(value, field)
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
    by_difficulty: mapping(
      data.by_difficulty,
      bucket,
      `${field}.by_difficulty`,
    ),
  }
}
function successRate(value: unknown): SuccessRateStats {
  const data = record(value, 'success_rate')
  return {
    ...bucket(data, 'success_rate'),
    avg_execution_time: number(
      data.avg_execution_time,
      'success_rate.avg_execution_time',
    ),
    by_difficulty: mapping(
      data.by_difficulty,
      bucket,
      'success_rate.by_difficulty',
    ),
    by_tag: mapping(data.by_tag, bucket, 'success_rate.by_tag'),
  }
}
function tokens(value: unknown): TokenStats {
  const data = record(value, 'tokens')
  return {
    total_tokens: number(data.total_tokens, 'tokens.total_tokens'),
    avg_tokens: number(data.avg_tokens, 'tokens.avg_tokens'),
    estimated_cost_usd: number(
      data.estimated_cost_usd,
      'tokens.estimated_cost_usd',
    ),
    unknown_cost_count: count(
      data.unknown_cost_count,
      'tokens.unknown_cost_count',
    ),
  }
}
function iterations(value: unknown): IterationStats {
  const data = record(value, 'iterations')
  return {
    known_count: count(data.known_count, 'iterations.known_count'),
    unknown_count: count(data.unknown_count, 'iterations.unknown_count'),
    average: nullable(data.average, number, 'iterations.average'),
    distribution: array(
      data.distribution,
      (value, field) => {
        const row = record(value, field)
        return {
          iterations: count(row.iterations, `${field}.iterations`),
          count: count(row.count, `${field}.count`),
        }
      },
      'iterations.distribution',
    ),
  }
}
function failureModes(value: unknown): FailureModeCounts {
  return mapping(value, count, 'failure_modes')
}
function successRateChart(value: unknown): SuccessRateChart {
  const data = record(value, 'success_rate_chart')
  return {
    points: array(
      data.points,
      (value, field) => {
        const row = record(value, field)
        return {
          name: text(row.name, `${field}.name`),
          success_rate: number(row.success_rate, `${field}.success_rate`, 1),
        }
      },
      'success_rate_chart.points',
    ),
  }
}
function tokenChart(value: unknown): TokenChart {
  const data = record(value, 'token_chart')
  return {
    series: array(
      data.series,
      (value, field) => {
        const row = record(value, field)
        return {
          name: text(row.name, `${field}.name`),
          points: array(
            row.points,
            (value, field) => {
              const point = record(value, field)
              return {
                problem_id: text(point.problem_id, `${field}.problem_id`),
                tokens: nullable(point.tokens, number, `${field}.tokens`),
              }
            },
            `${field}.points`,
          ),
        }
      },
      'token_chart.series',
    ),
  }
}
function costAccuracy(value: unknown): CostAccuracyChart {
  const data = record(value, 'cost_accuracy')
  return {
    points: array(
      data.points,
      (value, field) => {
        const row = record(value, field)
        return {
          name: text(row.name, `${field}.name`),
          success_rate: number(row.success_rate, `${field}.success_rate`, 1),
          estimated_cost_usd: number(
            row.estimated_cost_usd,
            `${field}.estimated_cost_usd`,
          ),
        }
      },
      'cost_accuracy.points',
    ),
  }
}
function capabilityRadar(value: unknown): CapabilityRadar {
  const data = record(value, 'capability_radar')
  const dimensions = array(data.dimensions, text, 'capability_radar.dimensions')
  return {
    dimensions,
    series: array(
      data.series,
      (value, field) => {
        const row = record(value, field)
        const scores = array(
          row.data,
          (value, field) => number(value, field, 100),
          `${field}.data`,
        )
        // 维度与分值按位对齐，长度不一致说明契约已变化。
        if (scores.length !== dimensions.length) protocol(`${field}.data`)
        return { name: nullable(row.name, text, `${field}.name`), data: scores }
      },
      'capability_radar.series',
    ),
    problem_counts: mapping(
      data.problem_counts,
      count,
      'capability_radar.problem_counts',
    ),
  }
}
function failuresByTag(value: unknown): FailuresByTag {
  const data = record(value, 'failures_by_tag')
  return { tags: mapping(data.tags, bucket, 'failures_by_tag.tags') }
}
function failureSummary(value: unknown): FailureSummary {
  const data = record(value, 'failure_summary')
  return {
    modes: mapping(data.modes, count, 'failure_summary.modes'),
    categories: mapping(data.categories, count, 'failure_summary.categories'),
    clusters: array(
      data.clusters,
      (value, field) => {
        const row = record(value, field)
        return {
          pattern: text(row.pattern, `${field}.pattern`, true),
          count: count(row.count, `${field}.count`),
          ...failureDiagnostic(row, field),
        }
      },
      'failure_summary.clusters',
    ),
  }
}
function failureCases(value: unknown): FailureCases {
  const data = record(value, 'failure_cases')
  return {
    items: array(
      data.items,
      (value, field) => {
        const row = record(value, field)
        return {
          problem_id: text(row.problem_id, `${field}.problem_id`),
          strategy: text(row.strategy, `${field}.strategy`),
          status: text(row.status, `${field}.status`),
          ...failureDiagnostic(row, field),
          error_message: nullable(
            row.error_message,
            (value, field) => text(value, field, true),
            `${field}.error_message`,
          ),
        }
      },
      'failure_cases.items',
    ),
  }
}
function strategyComparison(value: unknown): StrategyComparison {
  const data = record(value, 'compare_strategies')
  return {
    strategies: array(
      data.strategies,
      strategy,
      'compare_strategies.strategies',
    ),
  }
}
function modelComparison(value: unknown): ModelComparison {
  const data = record(value, 'compare_models')
  return {
    models: array(
      data.models,
      (value, field) => {
        const row = record(value, field)
        return {
          model: nullable(row.model, text, `${field}.model`),
          strategies: array(row.strategies, strategy, `${field}.strategies`),
        }
      },
      'compare_models.models',
    ),
  }
}
function historyComparison(value: unknown): HistoryComparison {
  const data = record(value, 'compare_history')
  return {
    series: array(
      data.series,
      (value, field) => {
        const row = record(value, field)
        return {
          run_id: nullable(row.run_id, text, `${field}.run_id`),
          completed_at: nullable(
            row.completed_at,
            text,
            `${field}.completed_at`,
          ),
          strategies: array(row.strategies, strategy, `${field}.strategies`),
        }
      },
      'compare_history.series',
    ),
  }
}
function runId(value: string): string {
  if (!value.trim()) throw new ApiClientError('缺少资源 ID')
  return value
}
function pathId(value: string): string {
  return encodeURIComponent(runId(value))
}
/** 只保留白名单内的非空筛选并去掉首尾空白（后端精确匹配）；全账号范围不带 run_id。 */
export function analyticsQuery(
  scope: AnalyticsScope,
  filters: AnalyticsFilters,
): Record<string, string> {
  const query: Record<string, string> = {}
  if (scope.kind === 'run') query.run_id = runId(scope.runId)
  for (const key of ['strategy', 'difficulty', 'tag'] as const) {
    const value = filters[key]?.trim()
    if (value) query[key] = value
  }
  return query
}

// 注入与 ReportDownloads 相同的已解包实例，沿用 Cookie、CSRF 和共享刷新。
export function createAnalyticsClient(http: AxiosInstance): AnalyticsClient {
  async function get<T>(
    url: string,
    read: (value: unknown) => T,
    params?: Record<string, string>,
    signal?: AbortSignal,
  ): Promise<T> {
    // 服务端全量聚合比列表读取慢，沿用实验分析的 20 s 上限。
    return read(
      await http.get<unknown, unknown>(url, {
        params,
        signal,
        timeout: 20_000,
      }),
    )
  }
  // async 让 ID/筛选校验失败以 rejection 返回，与网络错误处理方式一致。
  const scoped =
    <T>(url: string, read: (value: unknown) => T) =>
    async (
      scope: AnalyticsScope,
      filters: AnalyticsFilters,
      signal?: AbortSignal,
    ) =>
      get(url, read, analyticsQuery(scope, filters), signal)
  return {
    successRate: scoped('/analytics/success-rate', successRate),
    tokens: scoped('/analytics/tokens', tokens),
    iterations: scoped('/analytics/iterations', iterations),
    failureModes: scoped('/analytics/failure-modes', failureModes),
    successRateChart: scoped(
      '/visualizations/success-rate-chart',
      successRateChart,
    ),
    tokenChart: scoped('/visualizations/token-chart', tokenChart),
    costAccuracy: scoped('/visualizations/cost-accuracy', costAccuracy),
    capabilityRadar: scoped(
      '/visualizations/capability-radar',
      capabilityRadar,
    ),
    failuresByTag: scoped('/failures/by-tag', failuresByTag),
    failureSummary: async (id, signal) =>
      get(`/failures/summary/${pathId(id)}`, failureSummary, undefined, signal),
    failureCases: async (id, signal) =>
      get(`/failures/cases/${pathId(id)}`, failureCases, undefined, signal),
    compareStrategies: async (id, signal) =>
      get(
        '/compare/strategies',
        strategyComparison,
        { run_id: runId(id) },
        signal,
      ),
    compareModels: (signal) =>
      get('/compare/models', modelComparison, undefined, signal),
    compareHistory: async (id, signal) =>
      get('/compare/history', historyComparison, { run_id: runId(id) }, signal),
  }
}
