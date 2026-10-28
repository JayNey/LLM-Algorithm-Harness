import { t } from '../i18n/core.ts'
export function probeStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ok: t('正常'),
    unavailable: t('不可用'),
    unknown: t('未知'),
    partial: t('部分可用'),
    degraded: t('降级'),
    not_checked: t('未检查'),
    not_configured: t('未配置'),
    disabled: t('已禁用'),
  }
  return labels[status] ?? status
}

export function formatUptime(seconds: number): string {
  if (seconds < 60) return t('{{value1}} 秒', { value1: Math.round(seconds) })
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return t('{{value1}} 分钟', { value1: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24)
    return t('{{value1}} 小时 {{value2}} 分', {
      value1: hours,
      value2: minutes % 60,
    })
  return t('{{value1}} 天 {{value2}} 小时', {
    value1: Math.floor(hours / 24),
    value2: hours % 24,
  })
}

export function formatBytes(bytes: number | null): string {
  if (bytes === null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 10) / 10}%`
}

export function formatMs(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 10) / 10} ms`
}

export function formatRatePerSecond(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100) / 100}/s`
}
