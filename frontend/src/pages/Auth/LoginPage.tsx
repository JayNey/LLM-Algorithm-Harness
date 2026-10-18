import { Alert, Button, Checkbox, Form, Input } from 'antd'
import { useRef, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiClientError } from '@/auth/http.ts'
import { validateLogin } from '@/auth/loginForm.ts'
import { sanitizeReturnPath } from '@/auth/returnPath.ts'
import { useAuthStore } from '@/store/auth.ts'

interface LoginInput {
  identity: string
  password: string
  remember: boolean
}

function loginLocationState(value: unknown): {
  from: string | null | undefined
  registered: boolean
} {
  if (typeof value !== 'object' || value === null) {
    return { from: undefined, registered: false }
  }
  const record = value as Record<string, unknown>
  const from =
    typeof record.from === 'string' ||
    record.from === null ||
    record.from === undefined
      ? (record.from as string | null | undefined)
      : undefined
  return { from, registered: record.registered === true }
}

function formFieldName(name: string): keyof LoginInput | null {
  if (name === 'identity' || name === 'username') return 'identity'
  if (name === 'password') return 'password'
  if (name === 'remember') return 'remember'
  return null
}

function fieldMessages(details: unknown): Record<string, string> | null {
  if (
    typeof details !== 'object' ||
    details === null ||
    Array.isArray(details)
  ) {
    return null
  }
  const entries = Object.entries(details)
  if (entries.length === 0) return null
  const messages: Record<string, string> = {}
  for (const [key, value] of entries) {
    if (typeof value !== 'string') return null
    messages[key] = value
  }
  return messages
}

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { from, registered } = loginLocationState(location.state)
  const pending = useRef(false)
  const [submitting, setSubmitting] = useState(false)
  const [formMessage, setFormMessage] = useState('')
  const {
    control,
    handleSubmit,
    setError,
    clearErrors,
    formState: { errors },
  } = useForm<LoginInput>({
    defaultValues: {
      identity: '',
      password: '',
      remember: false,
    },
  })

  async function onSubmit(values: LoginInput) {
    if (pending.current) return
    clearErrors()
    setFormMessage('')
    const clientErrors = validateLogin(values)
    for (const name of ['identity', 'password'] as const) {
      const message = clientErrors[name]
      if (message) setError(name, { type: 'validate', message })
    }
    if (Object.keys(clientErrors).length > 0) return

    pending.current = true
    setSubmitting(true)
    try {
      await useAuthStore
        .getState()
        .login(values.identity, values.password, values.remember)
      navigate(sanitizeReturnPath(from))
    } catch (error) {
      if (!(error instanceof ApiClientError)) {
        setFormMessage('服务暂时不可用')
        return
      }
      if (error.status === 401) {
        setFormMessage('登录失败')
        return
      }
      if (error.status === 429) {
        setFormMessage('请求过于频繁，请稍后再试')
        return
      }
      if (error.status === 400) {
        const messages = fieldMessages(error.details)
        if (messages) {
          const extras: string[] = []
          for (const [name, message] of Object.entries(messages)) {
            const field = formFieldName(name)
            if (field) {
              setError(field, { type: 'server', message })
            } else {
              extras.push(message)
            }
          }
          if (extras.length > 0) setFormMessage(extras.join('；'))
          return
        }
        setFormMessage('请求无效')
        return
      }
      setFormMessage(error.message)
    } finally {
      pending.current = false
      setSubmitting(false)
    }
  }

  return (
    <section className="mx-auto w-full max-w-md">
      <h1 className="mb-4 text-xl font-semibold">登录</h1>
      {registered ? (
        <Alert className="mb-4" type="success" message="可以登录" showIcon />
      ) : null}
      {formMessage ? (
        <Alert className="mb-4" type="error" message={formMessage} showIcon />
      ) : null}
      <Form
        layout="vertical"
        noValidate
        onFinish={() => {
          void handleSubmit(onSubmit)()
        }}
      >
        <Form.Item
          label="用户名或邮箱"
          validateStatus={errors.identity ? 'error' : undefined}
          help={errors.identity?.message}
        >
          <Controller
            name="identity"
            control={control}
            render={({ field }) => (
              <Input id="login-identity" autoComplete="username" {...field} />
            )}
          />
        </Form.Item>
        <Form.Item
          label="密码"
          validateStatus={errors.password ? 'error' : undefined}
          help={errors.password?.message}
        >
          <Controller
            name="password"
            control={control}
            render={({ field }) => (
              <Input.Password
                id="login-password"
                autoComplete="current-password"
                {...field}
              />
            )}
          />
        </Form.Item>
        <Form.Item>
          <Controller
            name="remember"
            control={control}
            render={({ field }) => (
              <Checkbox
                id="login-remember"
                checked={field.value}
                onChange={(event) => field.onChange(event.target.checked)}
              >
                记住我
              </Checkbox>
            )}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting} block>
          登录
        </Button>
      </Form>
      <p className="mt-4">
        <Link to="/register">注册</Link>
      </p>
    </section>
  )
}
