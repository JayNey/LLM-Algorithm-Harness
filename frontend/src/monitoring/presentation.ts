export function probeStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ok: '正常',
    unavailable: '不可用',
    unknown: '未知',
    partial: '部分可用',
    degraded: '降级',
    not_checked: '未检查',
    not_configured: '未配置',
    disabled: '已禁用',
  }
  return labels[status] ?? status
}

export function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} 秒`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时 ${minutes % 60} 分`
  return `${Math.floor(hours / 24)} 天 ${hours % 24} 小时`
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
