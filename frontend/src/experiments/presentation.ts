import type { ExperimentDraft, ExperimentStatus } from './types.ts'

const statusLabels: Record<ExperimentStatus, string> = {
  pending: '排队中',
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  failed: '已失败',
  cancelled: '已取消',
}

export function statusLabel(status: string): string {
  return (statusLabels as Record<string, string>)[status] ?? status
}

export const executionLabels: Record<string, string> = {
  serial: '串行',
  parallel: '并行',
}

export const budgetKindLabels: Record<string, string> = {
  none: '不限制',
  max_calls: '调用次数',
  max_tokens: 'token 数',
  max_seconds: '时间（秒）',
}

export function formatUsd(value: number | null): string {
  if (value === null) return '成本未知'
  return `${value.toFixed(4)} USD`
}

export function formatAccuracy(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

export function formatDateTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '时间未知'
    : date.toLocaleString('zh-CN')
}

export function summarizeDraft(draft: ExperimentDraft): string {
  const parts: string[] = []
  if (draft.budget_kind !== 'none')
    parts.push(`${budgetKindLabels[draft.budget_kind]} ≤ ${draft.budget_value}`)
  if (draft.execution === 'parallel') parts.push(`并行 ×${draft.max_workers}`)
  return parts.join(' · ')
}
