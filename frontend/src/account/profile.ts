import dayjs from 'dayjs'
import { validateEmail, validateUsername } from '../auth/registerForm.ts'

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

export interface ProfileInput {
  username: string
  email: string
}

export function validateProfile(input: ProfileInput): Record<string, string> {
  const errors: Record<string, string> = {}
  const username = validateUsername(input.username)
  const email = validateEmail(input.email)
  if (username) errors.username = username
  if (email) errors.email = email
  return errors
}
