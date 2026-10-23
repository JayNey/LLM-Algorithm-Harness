export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '排队中',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '已失败',
    cancelled: '已取消',
  }
  return labels[status] ?? status
}

export function formatRate(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

export function formatDiff(value: number | null): string {
  if (value === null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)}%`
}

export function testMethodLabel(test: string): string {
  const labels: Record<string, string> = {
    fisher_exact: 'Fisher 精确检验',
    chi_square: '卡方检验',
    unavailable: '样本不足，无法检验',
  }
  return labels[test] ?? test
}

export function formatDateTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '时间未知'
    : date.toLocaleString('zh-CN')
}
