import type {
  Evaluation,
  ResultAvailability,
  ResultDetail,
  StrategySummary,
} from './types.ts'

const labels: Record<string, string> = {
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export function evaluationLabel(evaluation: Evaluation): string {
  if (evaluation.status === 'pending')
    return evaluation.can_start ? '待启动' : '已入队，等待执行'
  return Object.hasOwn(labels, evaluation.status)
    ? labels[evaluation.status]
    : `未知状态（${evaluation.status}）`
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
    if (recorded_units === 0) kind = 'empty'
    else if (evaluation.status !== 'completed') kind = 'partial'
    else
      kind = result.problems.total < expected_units ? 'incomplete' : 'complete'
  }
  return { kind, recorded_units, expected_units }
}

export function metricLabel(value: number | null, unit = ''): string {
  if (value === null || !Number.isFinite(value)) return '未知'
  return `${value}${unit ? ` ${unit}` : ''}`
}

export function successRateLabel(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '未知'
  return `${Number((value * 100).toFixed(2))}%`
}

export function resultStatusLabel(status: string): string {
  if (status === 'pending') return '待执行'
  return Object.hasOwn(labels, status)
    ? labels[status]
    : `未知状态（${status}）`
}

export function resultCostLabel(
  strategy: Pick<StrategySummary, 'estimated_cost_usd' | 'unknown_cost_count'>,
): string {
  const cost = metricLabel(strategy.estimated_cost_usd, 'USD')
  if (!strategy.unknown_cost_count) return cost
  return `${strategy.estimated_cost_usd ? `已知估算 ${cost}；` : ''}${strategy.unknown_cost_count} 条成本未知`
}
