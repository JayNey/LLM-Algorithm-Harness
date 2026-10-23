import type { AxiosInstance } from 'axios'
import { ApiClientError } from '../auth/http.ts'
import type {
  ApiPage,
  ComparisonReport,
  CostEffectivenessRow,
  ExperimentClient,
  ExperimentConfig,
  ExperimentJob,
  ListQuery,
  OptimizeAdvisory,
  PanelData,
  ParetoResult,
  SignificanceRow,
  TaskSnapshot,
  WinRateRow,
} from './types.ts'

function protocol(field: string): never {
  throw new ApiClientError('实验接口响应格式不兼容', undefined, { field })
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
function nullableNumber(value: unknown, field: string): number | null {
  return nullable(value, number, field)
}

function experimentConfig(value: unknown, field: string): ExperimentConfig {
  const data = record(value, field)
  const execution = text(data.execution, `${field}.execution`)
  if (execution !== 'serial' && execution !== 'parallel')
    protocol(`${field}.execution`)
  const budget =
    data.budget === null
      ? null
      : (() => {
          const raw = record(data.budget, `${field}.budget`)
          return {
            ...(raw.max_calls !== undefined
              ? {
                  max_calls:
                    nullableNumber(
                      raw.max_calls,
                      `${field}.budget.max_calls`,
                    ) ?? undefined,
                }
              : {}),
            ...(raw.max_tokens !== undefined
              ? {
                  max_tokens:
                    nullableNumber(
                      raw.max_tokens,
                      `${field}.budget.max_tokens`,
                    ) ?? undefined,
                }
              : {}),
            ...(raw.max_seconds !== undefined
              ? {
                  max_seconds:
                    nullableNumber(
                      raw.max_seconds,
                      `${field}.budget.max_seconds`,
                    ) ?? undefined,
                }
              : {}),
          }
        })()
  return {
    name: text(data.name, `${field}.name`, true),
    dataset_path: text(data.dataset_path, `${field}.dataset_path`),
    models: array(
      data.models,
      (value, field) => {
        const row = record(value, field)
        return {
          model: text(row.model, `${field}.model`),
          ...(row.base_url !== undefined && row.base_url !== null
            ? { base_url: text(row.base_url, `${field}.base_url`) }
            : {}),
          ...(row.temperature !== undefined && row.temperature !== null
            ? {
                temperature: number(row.temperature, `${field}.temperature`, 2),
              }
            : {}),
          ...(row.api_key_id !== undefined && row.api_key_id !== null
            ? { api_key_id: text(row.api_key_id, `${field}.api_key_id`) }
            : {}),
        }
      },
      `${field}.models`,
    ),
    strategies: array(
      data.strategies,
      (value, field) => {
        const row = record(value, field)
        return {
          name: text(row.name, `${field}.name`),
        }
      },
      `${field}.strategies`,
    ),
    repeats: count(data.repeats, `${field}.repeats`),
    budget,
    execution,
    max_workers: count(data.max_workers, `${field}.max_workers`),
  }
}

function job(value: unknown, field = 'experiment'): ExperimentJob {
  const data = record(value, field)
  return {
    id: text(data.id, `${field}.id`),
    name: text(data.name, `${field}.name`, true),
    status: text(data.status, `${field}.status`),
    config: experimentConfig(data.config, `${field}.config`),
    error_message: nullable(
      data.error_message,
      (value, field) => text(value, field, true),
      `${field}.error_message`,
    ),
    created_at: text(data.created_at, `${field}.created_at`),
    updated_at: text(data.updated_at, `${field}.updated_at`),
  }
}

function taskSnapshot(value: unknown, field = 'task'): TaskSnapshot {
  const data = record(value, field)
  const progress =
    data.progress === null
      ? null
      : (() => {
          const raw = record(data.progress, `${field}.progress`)
          return {
            current: count(raw.current, `${field}.progress.current`),
            total: count(raw.total, `${field}.progress.total`),
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
    task_type: text(data.task_type, `${field}.task_type`),
    entity_id: text(data.entity_id, `${field}.entity_id`),
    status: text(data.status, `${field}.status`),
    progress,
    error_message: nullable(
      data.error_message,
      (value, field) => text(value, field, true),
      `${field}.error_message`,
    ),
    created_at: text(data.created_at, `${field}.created_at`),
    updated_at: text(data.updated_at, `${field}.updated_at`),
  }
}

function combination(value: unknown, field: string) {
  const data = record(value, field)
  const denominator = record(data.denominator, `${field}.denominator`)
  const formal = record(data.formal, `${field}.formal`)
  const cost = record(data.cost, `${field}.cost`)
  return {
    combo_id: text(data.combo_id, `${field}.combo_id`),
    model: text(data.model, `${field}.model`),
    strategy: text(data.strategy, `${field}.strategy`),
    repeat: count(data.repeat, `${field}.repeat`),
    token_budget_unsupported: boolean(
      data.token_budget_unsupported,
      `${field}.token_budget_unsupported`,
    ),
    denominator: {
      total: count(denominator.total, `${field}.denominator.total`),
      completed: count(denominator.completed, `${field}.denominator.completed`),
      budget_exhausted: count(
        denominator.budget_exhausted,
        `${field}.denominator.budget_exhausted`,
      ),
    },
    solved: count(data.solved, `${field}.solved`),
    pass_rate_over_total: nullableNumber(
      data.pass_rate_over_total,
      `${field}.pass_rate_over_total`,
    ),
    formal: {
      evaluable: count(formal.evaluable, `${field}.formal.evaluable`),
      solved: count(formal.solved, `${field}.formal.solved`),
      rate: nullableNumber(formal.rate, `${field}.formal.rate`),
    },
    cost: {
      total_cost_usd: nullableNumber(
        cost.total_cost_usd,
        `${field}.cost.total_cost_usd`,
      ),
      known: boolean(cost.known, `${field}.cost.known`),
    },
  }
}

function winRateRow(value: unknown, field: string): WinRateRow {
  const data = record(value, field)
  const against = record(data.against, `${field}.against`)
  return {
    model: text(data.model, `${field}.model`),
    solved: count(data.solved, `${field}.solved`),
    against: Object.fromEntries(
      Object.entries(against).map(([key, value]) => {
        const row = record(value, `${field}.against.${key}`)
        return [
          key,
          {
            wins: count(row.wins, `${field}.against.${key}.wins`),
            ties: count(row.ties, `${field}.against.${key}.ties`),
            losses: count(row.losses, `${field}.against.${key}.losses`),
            win_rate: nullableNumber(
              row.win_rate,
              `${field}.against.${key}.win_rate`,
            ),
          },
        ]
      }),
    ),
  }
}

function significanceRow(value: unknown, field: string): SignificanceRow {
  const data = record(value, field)
  return {
    discordant_pairs: count(data.discordant_pairs, `${field}.discordant_pairs`),
    p_value: nullableNumber(data.p_value, `${field}.p_value`),
    significant: nullable(data.significant, boolean, `${field}.significant`),
    note: text(data.note, `${field}.note`, true),
    ...(data.a !== undefined && data.a !== null
      ? { a: text(data.a, `${field}.a`) }
      : {}),
    ...(data.b !== undefined && data.b !== null
      ? { b: text(data.b, `${field}.b`) }
      : {}),
  }
}

function costEffectiveness(
  value: unknown,
  field: string,
): CostEffectivenessRow {
  const data = record(value, field)
  return {
    model: text(data.model, `${field}.model`),
    solved: count(data.solved, `${field}.solved`),
    total_cost_usd: number(data.total_cost_usd, `${field}.total_cost_usd`),
    solved_per_usd: number(data.solved_per_usd, `${field}.solved_per_usd`),
  }
}

function comparison(value: unknown): ComparisonReport {
  const data = record(value, 'comparison')
  const modelComparison = record(
    data.model_comparison,
    'comparison.model_comparison',
  )
  const strategies = record(
    modelComparison.strategies,
    'comparison.model_comparison.strategies',
  )
  return {
    experiment: (() => {
      const meta = record(data.experiment, 'comparison.experiment')
      return {
        experiment_id: text(
          meta.experiment_id,
          'comparison.experiment.experiment_id',
        ),
        name: text(meta.name, 'comparison.experiment.name', true),
      }
    })(),
    combinations: array(
      data.combinations,
      combination,
      'comparison.combinations',
    ),
    model_comparison: {
      strategies: Object.fromEntries(
        Object.entries(strategies).map(([key, value]) => {
          const group = record(
            value,
            `comparison.model_comparison.strategies.${key}`,
          )
          return [
            key,
            {
              matrix: array(
                group.matrix,
                winRateRow,
                `…strategies.${key}.matrix`,
              ),
              significance: array(
                group.significance,
                significanceRow,
                `…strategies.${key}.significance`,
              ),
            },
          ]
        }),
      ),
      cost_effectiveness: array(
        modelComparison.cost_effectiveness,
        costEffectiveness,
        'comparison.model_comparison.cost_effectiveness',
      ),
    },
  }
}

function panel(value: unknown): PanelData {
  const data = record(value, 'panel')
  const datasets = (value: unknown, field: string) =>
    array(
      record(value, field).datasets,
      (value, field) => ({
        label: text(record(value, field).label, `${field}.label`, true),
        values: array(record(value, field).values, number, `${field}.values`),
      }),
      `${field}.datasets`,
    )
  const radar = record(data.radar, 'panel.radar')
  const bar = record(data.bar, 'panel.bar')
  return {
    radar: {
      labels: array(radar.labels, text, 'panel.radar.labels'),
      datasets: datasets(data.radar, 'panel.radar'),
    },
    scatter: array(
      data.scatter,
      (value, field) => {
        const row = record(value, field)
        return {
          label: text(row.label, `${field}.label`, true),
          x: number(row.x, `${field}.x`),
          y: number(row.y, `${field}.y`),
        }
      },
      'panel.scatter',
    ),
    bar: {
      labels: array(bar.labels, text, 'panel.bar.labels'),
      calls: array(bar.calls, count, 'panel.bar.calls'),
      elapsed: array(bar.elapsed, number, 'panel.bar.elapsed'),
      tokens: array(bar.tokens, count, 'panel.bar.tokens'),
    },
    matrix_tables: array(
      data.matrix_tables,
      (value, field) => {
        const row = record(value, field)
        return {
          strategy: text(row.strategy, `${field}.strategy`),
          rows: array(
            row.rows,
            (value, field) => {
              const item = record(value, field)
              return {
                model: text(item.model, `${field}.model`),
                solved: count(item.solved, `${field}.solved`),
                cells: array(
                  item.cells,
                  (value, field) => {
                    const cell = record(value, field)
                    return {
                      opponent: text(cell.opponent, `${field}.opponent`, true),
                      text: text(cell.text, `${field}.text`, true),
                    }
                  },
                  `${field}.cells`,
                ),
              }
            },
            `${field}.rows`,
          ),
        }
      },
      'panel.matrix_tables',
    ),
    algorithm_radar: (() => {
      const algorithm = record(data.algorithm_radar, 'panel.algorithm_radar')
      return {
        labels: array(algorithm.labels, text, 'panel.algorithm_radar.labels'),
        datasets: datasets(data.algorithm_radar, 'panel.algorithm_radar'),
      }
    })(),
  }
}

function pareto(value: unknown): ParetoResult {
  const data = record(value, 'pareto')
  return {
    accuracy_metric: text(data.accuracy_metric, 'pareto.accuracy_metric'),
    points: array(
      data.points,
      (value, field) => {
        const row = record(value, field)
        return {
          id: text(row.id, `${field}.id`),
          model: text(row.model, `${field}.model`),
          strategy: text(row.strategy, `${field}.strategy`),
          repeats: count(row.repeats, `${field}.repeats`),
          mean_cost_usd: number(row.mean_cost_usd, `${field}.mean_cost_usd`),
          mean_accuracy: number(row.mean_accuracy, `${field}.mean_accuracy`, 1),
          expected_solved_per_usd: nullableNumber(
            row.expected_solved_per_usd,
            `${field}.expected_solved_per_usd`,
          ),
          pareto_optimal: boolean(
            row.pareto_optimal,
            `${field}.pareto_optimal`,
          ),
          dominated_by: array(row.dominated_by, text, `${field}.dominated_by`),
        }
      },
      'pareto.points',
    ),
    frontier_ids: array(data.frontier_ids, text, 'pareto.frontier_ids'),
    best_value: (() => {
      const row = record(data.best_value, 'pareto.best_value')
      return {
        feasible: boolean(row.feasible, 'pareto.best_value.feasible'),
        point_id: nullable(
          row.point_id,
          (value, field) => text(value, field, true),
          'pareto.best_value.point_id',
        ),
        basis: text(row.basis, 'pareto.best_value.basis', true),
      }
    })(),
    budget_recommendations: array(
      data.budget_recommendations,
      (value, field) => {
        const row = record(value, field)
        return {
          budget_usd: number(row.budget_usd, `${field}.budget_usd`),
          feasible: boolean(row.feasible, `${field}.feasible`),
          point_id: nullable(
            row.point_id,
            (value, field) => text(value, field, true),
            `${field}.point_id`,
          ),
        }
      },
      'pareto.budget_recommendations',
    ),
  }
}

function advisory(value: unknown): OptimizeAdvisory {
  const data = record(value, 'advisory')
  const ranking = record(data.ranking, 'advisory.ranking')
  const recommendations = record(
    data.recommendations,
    'advisory.recommendations',
  )
  const budgetPlan =
    data.budget_plan === undefined || data.budget_plan === null
      ? undefined
      : (() => {
          const row = record(data.budget_plan, 'advisory.budget_plan')
          return {
            budget: number(row.budget, 'advisory.budget_plan.budget'),
            ...(row.min_accuracy !== undefined
              ? {
                  min_accuracy:
                    nullableNumber(
                      row.min_accuracy,
                      'advisory.budget_plan.min_accuracy',
                    ) ?? 0,
                }
              : {}),
            ...(row.estimated_cost !== undefined
              ? {
                  estimated_cost:
                    nullableNumber(
                      row.estimated_cost,
                      'advisory.budget_plan.estimated_cost',
                    ) ?? 0,
                }
              : {}),
            ...(row.estimated_accuracy !== undefined
              ? {
                  estimated_accuracy:
                    nullableNumber(
                      row.estimated_accuracy,
                      'advisory.budget_plan.estimated_accuracy',
                    ) ?? 0,
                }
              : {}),
            ...(row.coverage !== undefined
              ? {
                  coverage:
                    nullableNumber(
                      row.coverage,
                      'advisory.budget_plan.coverage',
                    ) ?? 0,
                }
              : {}),
          }
        })()
  return {
    generated_at: text(data.generated_at, 'advisory.generated_at'),
    selected_objective: text(
      data.selected_objective,
      'advisory.selected_objective',
    ),
    ranking: {
      ranking: array(
        ranking.ranking,
        (value, field) => {
          const row = record(value, field)
          return {
            model: text(row.model, `${field}.model`),
            strategy: text(row.strategy, `${field}.strategy`),
            accuracy: nullableNumber(row.accuracy, `${field}.accuracy`),
            cost_usd: nullableNumber(row.cost_usd, `${field}.cost_usd`),
            ratio: nullableNumber(row.ratio, `${field}.ratio`),
          }
        },
        'advisory.ranking.ranking',
      ),
    },
    recommendations: Object.fromEntries(
      Object.entries(recommendations).map(([key, value]) => {
        const row = record(value, `advisory.recommendations.${key}`)
        return [
          key,
          {
            objective: text(row.objective, `${key}.objective`),
            feasible: boolean(row.feasible, `${key}.feasible`),
            ...(row.basis !== undefined
              ? { basis: text(row.basis, `${key}.basis`, true) }
              : {}),
            ...(row.note !== undefined
              ? { note: text(row.note, `${key}.note`, true) }
              : {}),
            ...(row.model !== undefined
              ? { model: text(row.model, `${key}.model`) }
              : {}),
            ...(row.strategy !== undefined
              ? { strategy: text(row.strategy, `${key}.strategy`) }
              : {}),
            ...(row.accuracy !== undefined
              ? {
                  accuracy:
                    nullableNumber(row.accuracy, `${key}.accuracy`) ?? 0,
                }
              : {}),
            ...(row.cost_usd !== undefined
              ? {
                  cost_usd:
                    nullableNumber(row.cost_usd, `${key}.cost_usd`) ?? 0,
                }
              : {}),
            ...(row.ratio !== undefined
              ? { ratio: nullableNumber(row.ratio, `${key}.ratio`) ?? 0 }
              : {}),
          },
        ]
      }),
    ),
    ...(budgetPlan ? { budget_plan: budgetPlan } : {}),
  } as OptimizeAdvisory
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
export function createExperimentClient(http: AxiosInstance): ExperimentClient {
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
  async function post<T>(
    url: string,
    read: (value: unknown) => T,
    data?: unknown,
    signal?: AbortSignal,
  ): Promise<T> {
    return read(
      await http.post<unknown, unknown>(url, data, { signal, timeout: 20_000 }),
    )
  }
  return {
    list: (query, signal) =>
      get(
        '/experiments',
        (value) => page(value, job, 'experiments'),
        listQuery(query),
        signal,
      ),
    get: async (id, signal) =>
      get(`/experiments/${pathId(id)}`, job, undefined, signal),
    create: async (payload) =>
      job(
        await http.post<unknown, unknown>('/experiments', payload, {
          timeout: 20_000,
        }),
      ),
    remove: async (id) => {
      await http.delete(`/experiments/${pathId(id)}`, { timeout: 20_000 })
    },
    run: async (id) => {
      const data = await http.post<unknown, unknown>(
        `/experiments/${pathId(id)}/run`,
        undefined,
        { timeout: 20_000 },
      )
      const row = record(data, 'run')
      return { ...job(row, 'run'), task_id: text(row.task_id, 'run.task_id') }
    },
    comparison: async (id, signal) =>
      get(
        `/experiments/${pathId(id)}/comparison`,
        comparison,
        undefined,
        signal,
        20_000,
      ),
    panel: async (id, signal) =>
      get(`/experiments/${pathId(id)}/panel`, panel, undefined, signal, 20_000),
    task: async (taskId, signal) =>
      get(`/tasks/${pathId(taskId)}`, taskSnapshot, undefined, signal),
    cancelTask: async (taskId) => {
      await http.delete(`/tasks/${pathId(taskId)}`, { timeout: 20_000 })
    },
    runningExperimentTasks: async (signal) => {
      // 后端 GET /tasks 只接受单个 status，running 与 paused 两次查询后按 id 去重；
      // paused 任务同样可取消，避免列表/详情对暂停实验出现「找不到任务」死角。
      const pages = await Promise.all(
        (['running', 'paused'] as const).map((status) =>
          get(
            '/tasks',
            (value) => page(value, taskSnapshot, 'tasks'),
            { task_type: 'experiment', status, limit: 100 },
            signal,
          ),
        ),
      )
      const seen = new Map<string, TaskSnapshot>()
      for (const result of pages)
        for (const item of result.items) seen.set(item.id, item)
      return [...seen.values()]
    },
    pareto: async (experimentId, budgets, accuracyMetric, signal) => {
      // 后端帕累托校验依赖原始报告（数据集指纹/token 预算标志等），
      // 因此这里取未解析的原始 comparison 作为 payload。
      const raw = await http.get<unknown, unknown>(
        `/experiments/${pathId(experimentId)}/comparison`,
        { signal, timeout: 20_000 },
      )
      return post(
        '/pareto/analyze',
        pareto,
        {
          comparisons: [raw],
          budgets,
          accuracy_metric: accuracyMetric,
        },
        signal,
      )
    },
    optimize: async (experimentId, options, signal) => {
      const raw = await http.get<unknown, unknown>(
        `/experiments/${pathId(experimentId)}/comparison`,
        { signal, timeout: 20_000 },
      )
      return post(
        '/optimize',
        advisory,
        {
          comparison: raw,
          ...(options.budget !== undefined ? { budget: options.budget } : {}),
          ...(options.minAccuracy !== undefined
            ? { min_accuracy: options.minAccuracy }
            : {}),
          objective: options.objective ?? 'best_value',
        },
        signal,
      )
    },
  }
}
