import { escapeHtml } from './text.ts'

export function loginWelcome(username: string | null): string {
  if (username && username.length > 0)
    return `欢迎回来，${escapeHtml(username)}`
  return '欢迎回来'
}
