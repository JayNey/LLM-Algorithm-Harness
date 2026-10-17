import { Alert, Button, Form, Input } from 'antd'
import { useRef, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { ApiClientError } from '@/auth/http.ts'
import {
  passwordStrength,
  validateRegistration,
  type RegistrationInput,
} from '@/auth/registerForm.ts'
import { useAuthStore } from '@/store/auth.ts'

const strengthText = {
  short: '不足 12 位',
  ok: '已达到 12 位',
  long: '16 位及以上',
} as const

function isRegistrationField(name: string): name is keyof RegistrationInput {
  return (
    name === 'username' ||
    name === 'email' ||
    name === 'password' ||
    name === 'confirmPassword'
  )
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

export default function RegisterPage() {
  const navigate = useNavigate()
  const pending = useRef(false)
  const [submitting, setSubmitting] = useState(false)
  const [formMessage, setFormMessage] = useState('')
  const {
    control,
    handleSubmit,
    setError,
    clearErrors,
    setValue,
    formState: { errors },
  } = useForm<RegistrationInput>({
    defaultValues: {
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    },
  })
  const password = useWatch({ control, name: 'password', defaultValue: '' })

  async function onSubmit(values: RegistrationInput) {
    if (pending.current) return
    clearErrors()
    setFormMessage('')
    const clientErrors = validateRegistration(values)
    const names = Object.keys(clientErrors)
    if (names.length > 0) {
      for (const name of names) {
        if (!isRegistrationField(name)) continue
        setError(name, { type: 'validate', message: clientErrors[name] })
      }
      return
    }

    pending.current = true
    setSubmitting(true)
    try {
      const client = useAuthStore.getState().httpClient()
      await client.post('/api/v1/auth/register', {
        username: values.username,
        email: values.email,
        password: values.password,
      })
      navigate('/login', { state: { registered: true } })
    } catch (error) {
      if (!(error instanceof ApiClientError)) {
        setFormMessage('服务暂时不可用')
        return
      }
      if (error.status === 409) {
        setFormMessage('用户名或邮箱不可用')
        setValue('password', '')
        setValue('confirmPassword', '')
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
            if (isRegistrationField(name)) {
              setError(name, { type: 'server', message })
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
      <h1 className="mb-4 text-xl font-semibold">注册</h1>
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
          label="用户名"
          validateStatus={errors.username ? 'error' : undefined}
          help={errors.username?.message}
        >
          <Controller
            name="username"
            control={control}
            render={({ field }) => (
              <Input
                id="register-username"
                autoComplete="username"
                {...field}
              />
            )}
          />
        </Form.Item>
        <Form.Item
          label="邮箱"
          validateStatus={errors.email ? 'error' : undefined}
          help={errors.email?.message}
        >
          <Controller
            name="email"
            control={control}
            render={({ field }) => (
              <Input
                id="register-email"
                type="email"
                autoComplete="email"
                {...field}
              />
            )}
          />
        </Form.Item>
        <Form.Item
          label="密码"
          validateStatus={errors.password ? 'error' : undefined}
          help={errors.password?.message}
          extra={strengthText[passwordStrength(password)]}
        >
          <Controller
            name="password"
            control={control}
            render={({ field }) => (
              <Input.Password
                id="register-password"
                autoComplete="new-password"
                {...field}
              />
            )}
          />
        </Form.Item>
        <Form.Item
          label="确认密码"
          validateStatus={errors.confirmPassword ? 'error' : undefined}
          help={errors.confirmPassword?.message}
        >
          <Controller
            name="confirmPassword"
            control={control}
            render={({ field }) => (
              <Input.Password
                id="register-confirm-password"
                autoComplete="new-password"
                {...field}
              />
            )}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting} block>
          注册
        </Button>
      </Form>
      <p className="mt-4">
        <Link to="/login">登录</Link>
      </p>
    </section>
  )
}
