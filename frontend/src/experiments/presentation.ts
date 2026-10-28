import { currentLanguage, t } from '../i18n/core.ts'
import type { ExperimentDraft, ExperimentStatus } from './types.ts'

const statusLabels: Record<ExperimentStatus, string> = {
  get pending() {
    return t('排队中')
  },
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
    return t('已失败')
  },
  get cancelled() {
    return t('已取消')
  },
}

export function statusLabel(status: string): string {
  return (statusLabels as Record<string, string>)[status] ?? status
}

export const executionLabels: Record<string, string> = {
  get serial() {
    return t('串行')
  },
  get parallel() {
    return t('并行')
  },
}

export const budgetKindLabels: Record<string, string> = {
  get none() {
    return t('不限制')
  },
  get max_calls() {
    return t('调用次数')
  },
  get max_tokens() {
    return t('token 数')
  },
  get max_seconds() {
    return t('时间（秒）')
  },
}

export function formatUsd(value: number | null): string {
  if (value === null) return t('成本未知')
  return `${value.toFixed(4)} USD`
}

export function formatAccuracy(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

export function formatDateTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? t('时间未知')
    : date.toLocaleString(currentLanguage())
}

export function summarizeDraft(draft: ExperimentDraft): string {
  const parts: string[] = []
  if (draft.budget_kind !== 'none')
    parts.push(`${budgetKindLabels[draft.budget_kind]} ≤ ${draft.budget_value}`)
  if (draft.execution === 'parallel')
    parts.push(t('并行 ×{{value1}}', { value1: draft.max_workers }))
  return parts.join(' · ')
}
