import { Alert, Button, Form, Input } from 'antd'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import {
  formatUnixSeconds,
  passwordChangePayload,
  readProfile,
  validatePasswordChange,
  validateProfile,
  wrongCurrentPassword,
  type PasswordChangeInput,
  type ProfileInput,
} from '@/account/profile.ts'
import { ApiClientError } from '@/auth/http.ts'
import { useAuthStore } from '@/store/auth.ts'

function failureText(error: unknown): string {
  if (!(error instanceof ApiClientError)) return '服务暂时不可用'
  if (error.status === 409) return '用户名或邮箱不可用'
  if (error.status === 400) return '请求无效'
  if (error.status === 429) return '请求过于频繁，请稍后再试'
  return '服务暂时不可用'
}

export default function ProfilePage() {
  const updateUsername = useAuthStore((state) => state.updateUsername)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [formMessage, setFormMessage] = useState('')
  const [saved, setSaved] = useState(false)
  const [createdAt, setCreatedAt] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [passwordMessage, setPasswordMessage] = useState('')
  const [passwordSaved, setPasswordSaved] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const {
    control,
    handleSubmit,
    setError,
    clearErrors,
    reset,
    formState: { errors },
  } = useForm<ProfileInput>({
    defaultValues: { username: '', email: '' },
  })
  const {
    control: passwordControl,
    handleSubmit: handlePasswordSubmit,
    setError: setPasswordError,
    clearErrors: clearPasswordErrors,
    reset: resetPassword,
    formState: { errors: passwordErrors },
  } = useForm<PasswordChangeInput>({
    defaultValues: {
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
    },
  })

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const profile = readProfile(
          await useAuthStore.getState().httpClient().get('/users/me'),
        )
        if (!active) return
        if (!profile) {
          setLoadError('服务暂时不可用')
          return
        }
        reset({ username: profile.username, email: profile.email })
        setCreatedAt(profile.created_at)
      } catch (error) {
        if (!active) return
        setLoadError(failureText(error))
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [reset])

  async function onSubmit(values: ProfileInput) {
    clearErrors()
    setFormMessage('')
    setSaved(false)
    const clientErrors = validateProfile(values)
    for (const name of ['username', 'email'] as const) {
      const message = clientErrors[name]
      if (message) setError(name, { type: 'validate', message })
    }
    if (Object.keys(clientErrors).length > 0) return

    setSubmitting(true)
    const previous = useAuthStore.getState().session?.username
    try {
      const profile = readProfile(
        await useAuthStore.getState().httpClient().patch('/users/me', {
          username: values.username,
          email: values.email,
        }),
      )
      if (!profile) {
        setFormMessage('服务暂时不可用')
        return
      }
      reset({ username: profile.username, email: profile.email })
      setCreatedAt(profile.created_at)
      if (profile.username !== previous) updateUsername(profile.username)
      setSaved(true)
    } catch (error) {
      setFormMessage(failureText(error))
    } finally {
      setSubmitting(false)
    }
  }

  async function onPasswordSubmit(values: PasswordChangeInput) {
    clearPasswordErrors()
    setPasswordMessage('')
    setPasswordSaved(false)
    const clientErrors = validatePasswordChange(values)
    for (const name of [
      'currentPassword',
      'newPassword',
      'confirmPassword',
    ] as const) {
      const message = clientErrors[name]
      if (message) setPasswordError(name, { type: 'validate', message })
    }
    const payload = passwordChangePayload(values)
    if (!payload) return

    setChangingPassword(true)
    try {
      await useAuthStore
        .getState()
        .httpClient()
        .post('/users/me/password', payload)
      resetPassword()
      setPasswordSaved(true)
    } catch (error) {
      if (
        error instanceof ApiClientError &&
        wrongCurrentPassword(error.message)
      ) {
        resetPassword()
        setPasswordMessage('当前密码不正确')
        return
      }
      setPasswordMessage(failureText(error))
    } finally {
      setChangingPassword(false)
    }
  }

  if (loading) return <p>加载中</p>
  if (loadError || createdAt === null) {
    return (
      <section>
        <h1>个人资料</h1>
        <Alert type="error" message={loadError || '服务暂时不可用'} showIcon />
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-md">
      <h1 className="mb-4 text-xl font-semibold">个人资料</h1>
      {saved ? (
        <Alert className="mb-4" type="success" message="已保存" showIcon />
      ) : null}
      {formMessage ? (
        <Alert className="mb-4" type="error" message={formMessage} showIcon />
      ) : null}
      <p className="mb-4">注册时间：{formatUnixSeconds(createdAt)}</p>
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
            render={({ field }) => <Input {...field} />}
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
            render={({ field }) => <Input type="email" {...field} />}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting}>
          保存
        </Button>
      </Form>
      <h2 className="mb-4 mt-8 text-lg font-semibold">修改密码</h2>
      {passwordSaved ? (
        <Alert className="mb-4" type="success" message="已更新" showIcon />
      ) : null}
      {passwordMessage ? (
        <Alert
          className="mb-4"
          type="error"
          message={passwordMessage}
          showIcon
        />
      ) : null}
      <Form
        layout="vertical"
        noValidate
        onFinish={() => {
          void handlePasswordSubmit(onPasswordSubmit)()
        }}
      >
        <Form.Item
          label="当前密码"
          validateStatus={passwordErrors.currentPassword ? 'error' : undefined}
          help={passwordErrors.currentPassword?.message}
        >
          <Controller
            name="currentPassword"
            control={passwordControl}
            render={({ field }) => (
              <Input.Password autoComplete="current-password" {...field} />
            )}
          />
        </Form.Item>
        <Form.Item
          label="新密码"
          validateStatus={passwordErrors.newPassword ? 'error' : undefined}
          help={passwordErrors.newPassword?.message}
        >
          <Controller
            name="newPassword"
            control={passwordControl}
            render={({ field }) => (
              <Input.Password autoComplete="new-password" {...field} />
            )}
          />
        </Form.Item>
        <Form.Item
          label="确认密码"
          validateStatus={passwordErrors.confirmPassword ? 'error' : undefined}
          help={passwordErrors.confirmPassword?.message}
        >
          <Controller
            name="confirmPassword"
            control={passwordControl}
            render={({ field }) => (
              <Input.Password autoComplete="new-password" {...field} />
            )}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={changingPassword}>
          更新密码
        </Button>
      </Form>
    </section>
  )
}
