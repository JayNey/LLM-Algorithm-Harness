import { t } from '../i18n/core.ts'
import { escapeHtml } from './text.ts'

export function loginWelcome(username: string | null): string {
  if (username && username.length > 0)
    return t('欢迎回来，{{name}}', { name: escapeHtml(username) })
  return t('欢迎回来')
}
