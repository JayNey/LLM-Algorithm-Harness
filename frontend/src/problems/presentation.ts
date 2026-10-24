export function difficultyLabel(difficulty: string | null): string {
  if (difficulty === null) return '难度未知'
  const labels: Record<string, string> = {
    easy: '简单',
    medium: '中等',
    hard: '困难',
  }
  return labels[difficulty] ?? difficulty
}

export function sourceLabel(source: string): string {
  return source === 'personal' ? '个人' : source === 'shared' ? '共享' : source
}

export function historyStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    passed: '通过',
    failed: '未通过',
    error: '执行错误',
    skipped: '跳过',
    pending: '等待中',
    running: '执行中',
  }
  return labels[status] ?? status
}

export function importStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '排队中',
    running: '导入中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    paused: '已暂停',
  }
  return labels[status] ?? status
}

export function formatRate(passed: number, total: number): string {
  return total === 0 ? '—' : `${Math.round((passed / total) * 100)}%`
}
