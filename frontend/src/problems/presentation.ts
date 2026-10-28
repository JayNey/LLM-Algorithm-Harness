import { t } from '../i18n/core.ts'
export function difficultyLabel(difficulty: string | null): string {
  if (difficulty === null) return t('难度未知')
  const labels: Record<string, string> = {
    easy: t('简单'),
    medium: t('中等'),
    hard: t('困难'),
  }
  return labels[difficulty] ?? difficulty
}

export function sourceLabel(source: string): string {
  return source === 'personal'
    ? t('个人')
    : source === 'shared'
      ? t('共享')
      : source
}

export function historyStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    passed: t('通过'),
    failed: t('未通过'),
    error: t('执行错误'),
    skipped: t('跳过'),
    pending: t('等待中'),
    running: t('执行中'),
  }
  return labels[status] ?? status
}

export function importStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: t('排队中'),
    running: t('导入中'),
    completed: t('已完成'),
    failed: t('失败'),
    cancelled: t('已取消'),
    paused: t('已暂停'),
  }
  return labels[status] ?? status
}

export function formatRate(passed: number, total: number): string {
  return total === 0 ? '—' : `${Math.round((passed / total) * 100)}%`
}
