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
  // 评测单元状态与后端口径一致（src/strategy_base.py 写入 success/
  // failed/error/unsupported/budget_exhausted，沙箱超时为 timeout）。
  const labels: Record<string, string> = {
    success: t('通过'),
    failed: t('未通过'),
    error: t('执行错误'),
    timeout: t('执行超时'),
    unsupported: t('不支持'),
    not_evaluable: t('不可评估（缺少测试用例）'),
    budget_exhausted: t('预算跳过'),
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
