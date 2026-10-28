import { currentLanguage, t } from '../i18n/core.ts'
export function runStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: t('排队中'),
    running: t('运行中'),
    paused: t('已暂停'),
    completed: t('已完成'),
    failed: t('已失败'),
    cancelled: t('已取消'),
  }
  return labels[status] ?? status
}

export function formatRate(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

export function formatUsd(value: number | null): string {
  return value === null ? t('成本未知') : `${value.toFixed(4)} USD`
}

export function formatGrowth(value: number | null): string {
  if (value === null) return t('数据不足')
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)}%`
}

export function formatDateTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? t('时间未知')
    : date.toLocaleString(currentLanguage())
}
