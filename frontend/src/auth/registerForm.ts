export interface RegistrationInput {
  username: string
  email: string
  password: string
  confirmPassword: string
}

const usernamePattern = /^[A-Za-z0-9_.-]+$/
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function validateUsername(username: string): string | undefined {
  if (
    username.length < 3 ||
    username.length > 64 ||
    !usernamePattern.test(username)
  ) {
    return '用户名需为 3–64 个字母、数字、下划线、点或连字符'
  }
  return undefined
}

export function validateEmail(email: string): string | undefined {
  if (email.length < 3 || email.length > 254 || !emailPattern.test(email)) {
    return '请输入有效邮箱'
  }
  return undefined
}

export function validateRegistration(
  input: RegistrationInput,
): Record<string, string> {
  const errors: Record<string, string> = {}
  const username = validateUsername(input.username)
  const email = validateEmail(input.email)
  if (username) errors.username = username
  if (email) errors.email = email

  if (input.password.length < 12) {
    errors.password = '至少 12 个字符'
  } else if (input.password.length > 1024) {
    errors.password = '密码不能超过 1024 个字符'
  }

  if (input.password !== input.confirmPassword) {
    errors.confirmPassword = '两次密码不一致'
  }

  return errors
}

export function passwordStrength(password: string): 'short' | 'ok' | 'long' {
  if (password.length < 12) return 'short'
  if (password.length >= 16) return 'long'
  return 'ok'
}
