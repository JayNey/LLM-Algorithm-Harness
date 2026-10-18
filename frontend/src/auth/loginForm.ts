export interface LoginFormInput {
  identity: string
  password: string
}

export function validateLogin(input: LoginFormInput): Record<string, string> {
  const errors: Record<string, string> = {}
  if (input.identity.length === 0) {
    errors.identity = '请输入用户名或邮箱'
  } else if (input.identity.length > 254) {
    errors.identity = '用户名或邮箱不能超过 254 个字符'
  }
  if (input.password.length === 0) {
    errors.password = '请输入密码'
  } else if (input.password.length > 1024) {
    errors.password = '密码不能超过 1024 个字符'
  }
  return errors
}
