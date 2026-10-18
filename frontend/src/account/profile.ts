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

export interface PasswordChangeInput {
  currentPassword: string
  newPassword: string
  confirmPassword: string
}

export function validatePasswordChange(
  input: PasswordChangeInput,
): Record<string, string> {
  const errors: Record<string, string> = {}
  if (input.currentPassword.length === 0) {
    errors.currentPassword = '请输入当前密码'
  }
  if (input.newPassword.length < 12) {
    errors.newPassword = '至少 12 个字符'
  } else if (input.newPassword.length > 1024) {
    errors.newPassword = '密码不能超过 1024 个字符'
  }
  if (input.newPassword !== input.confirmPassword) {
    errors.confirmPassword = '两次密码不一致'
  }
  return errors
}

export function passwordChangePayload(
  input: PasswordChangeInput,
): { current_password: string; new_password: string } | null {
  if (Object.keys(validatePasswordChange(input)).length > 0) return null
  return {
    current_password: input.currentPassword,
    new_password: input.newPassword,
  }
}

export function wrongCurrentPassword(message: string): boolean {
  return message === '当前密码不正确'
}
