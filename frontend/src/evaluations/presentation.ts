import { t } from '../i18n/core.ts'
import type {
  Evaluation,
  ResultAvailability,
  ResultDetail,
  StrategySummary,
} from './types.ts'

const labels: Record<string, string> = {
  get running() {
    return t('运行中')
  },
  get paused() {
    return t('已暂停')
  },
  get completed() {
    return t('已完成')
  },
  get failed() {
    return t('失败')
  },
  get cancelled() {
    return t('已取消')
  },
}

export function evaluationLabel(evaluation: Evaluation): string {
  if (evaluation.status === 'pending')
    return evaluation.can_start ? t('待启动') : t('已入队，等待执行')
  return Object.hasOwn(labels, evaluation.status)
    ? labels[evaluation.status]
    : t('未知状态（{{value1}}）', { value1: evaluation.status })
}

export function resultAvailability(
  evaluation: Evaluation,
  result: ResultDetail | null | undefined,
): ResultAvailability {
  const expected_units = evaluation.execution_progress.total_units
  const recorded_units = result?.problems.total ?? null
  let kind: ResultAvailability['kind'] = 'unknown'
  if (
    result &&
    result.status === evaluation.status &&
    [
      'pending',
      'running',
      'paused',
      'completed',
      'failed',
      'cancelled',
    ].includes(evaluation.status)
  ) {
    if (evaluation.status === 'completed')
      kind =
        recorded_units === 0
          ? 'empty'
          : result.problems.total < expected_units
            ? 'incomplete'
            : 'complete'
    else if (evaluation.status === 'pending' || evaluation.status === 'running')
      kind = recorded_units === 0 ? 'waiting' : 'partial'
    else if (evaluation.status === 'paused') kind = 'paused'
    else if (evaluation.status === 'failed') kind = 'failed'
    else if (evaluation.status === 'cancelled') kind = 'cancelled'
  }
  return { kind, recorded_units, expected_units }
}

export function metricLabel(value: number | null, unit = ''): string {
  if (value === null || !Number.isFinite(value)) return t('未知')
  return `${value}${unit ? ` ${unit}` : ''}`
}

export function successRateLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return t('未知')
  return `${Number((value * 100).toFixed(2))}%`
}

export function resultStatusLabel(status: string): string {
  if (status === 'pending') return t('待执行')
  return Object.hasOwn(labels, status)
    ? labels[status]
    : t('未知状态（{{value1}}）', { value1: status })
}

export function resultCostLabel(
  strategy: Pick<StrategySummary, 'estimated_cost_usd' | 'unknown_cost_count'>,
): string {
  const cost = metricLabel(strategy.estimated_cost_usd, 'USD')
  if (!strategy.unknown_cost_count) return cost
  return t('{{value1}}{{value2}} 条成本未知', {
    value1: strategy.estimated_cost_usd
      ? t('已知估算 {{value1}}；', { value1: cost })
      : '',
    value2: strategy.unknown_cost_count,
  })
}
