import dayjs from 'dayjs'

export interface UserProfile {
  username: string
  email: string
  created_at: number
}

export function readProfile(value: unknown): UserProfile | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (
    typeof record.username !== 'string' ||
    typeof record.email !== 'string' ||
    typeof record.created_at !== 'number'
  ) {
    return null
  }
  return {
    username: record.username,
    email: record.email,
    created_at: record.created_at,
  }
}

export function formatUnixSeconds(seconds: number): string {
  return dayjs.unix(seconds).format('YYYY-MM-DD HH:mm')
}
