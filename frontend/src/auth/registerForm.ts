export interface RegistrationInput {
  username: string
  email: string
  password: string
  confirmPassword: string
}

const usernamePattern = /^[A-Za-z0-9_.-]+$/

export function validateRegistration(
  input: RegistrationInput,
): Record<string, string> {
  const errors: Record<string, string> = {}

  if (
    input.username.length < 3 ||
    input.username.length > 64 ||
    !usernamePattern.test(input.username)
  ) {
    errors.username = '用户名需为 3–64 个字母、数字、下划线、点或连字符'
  }

  if (
    input.email.length < 3 ||
    input.email.length > 254 ||
    !input.email.includes('@') ||
    !input.email.includes('.')
  ) {
    errors.email = '请输入有效邮箱'
  }

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
