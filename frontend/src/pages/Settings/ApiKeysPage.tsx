import { Alert, Button, Form, Input, Select } from 'antd'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import {
  groupApiKeys,
  lastUsedLabel,
  providers,
  readApiKeys,
  rejectApiKey,
  validateKeyName,
  type ApiKeyRecord,
  type Provider,
} from '@/account/apiKeys.ts'
import { formatUnixSeconds } from '@/account/profile.ts'
import { useAuthStore } from '@/store/auth.ts'

interface AddInput {
  provider: Provider
  key_name: string
  api_key: string
}

function KeyRow({ item }: { item: ApiKeyRecord }) {
  return (
    <li>
      <p>{item.key_name}</p>
      <p>{item.provider}</p>
      <p>创建时间：{formatUnixSeconds(item.created_at)}</p>
      <p>{item.verified ? '已验证' : '未验证'}</p>
      <p>使用次数：{item.usage_count}</p>
      <p>
        {item.last_used_at === null
          ? lastUsedLabel(null)
          : `最后使用：${formatUnixSeconds(item.last_used_at)}`}
      </p>
    </li>
  )
}

export default function ApiKeysPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [keys, setKeys] = useState<ApiKeyRecord[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [formMessage, setFormMessage] = useState('')
  const {
    control,
    handleSubmit,
    reset,
    setError: setFieldError,
    formState: { errors },
  } = useForm<AddInput>({
    defaultValues: { provider: 'openai', key_name: '', api_key: '' },
  })

  async function load() {
    const parsed = readApiKeys(
      await useAuthStore.getState().httpClient().get('/api-keys'),
    )
    if (!parsed) {
      setError('服务暂时不可用')
      setKeys([])
      return
    }
    setError('')
    setKeys(parsed)
  }

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        if (active) await load()
      } catch {
        if (active) setError('服务暂时不可用')
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [])

  async function onSubmit(values: AddInput) {
    setFormMessage('')
    const nameError = validateKeyName(values.key_name)
    const keyError = rejectApiKey(values.api_key)
    if (nameError)
      setFieldError('key_name', { type: 'validate', message: nameError })
    if (keyError)
      setFieldError('api_key', { type: 'validate', message: keyError })
    if (nameError || keyError) return
    setSubmitting(true)
    try {
      await useAuthStore.getState().httpClient().post('/api-keys', {
        provider: values.provider,
        key_name: values.key_name,
        api_key: values.api_key,
      })
      reset({ provider: 'openai', key_name: '', api_key: '' })
      await load()
    } catch {
      setFormMessage('服务暂时不可用')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <p>加载中</p>
  if (error) {
    return (
      <section>
        <h1>API 密钥</h1>
        <Alert type="error" message={error} showIcon />
      </section>
    )
  }

  const groups = groupApiKeys(keys)
  return (
    <section>
      <h1>API 密钥</h1>
      <p>密钥保存后不再显示</p>
      {formMessage ? (
        <Alert type="error" message={formMessage} showIcon />
      ) : null}
      <Form
        layout="vertical"
        noValidate
        onFinish={() => {
          void handleSubmit(onSubmit)()
        }}
      >
        <Form.Item label="提供商">
          <Controller
            name="provider"
            control={control}
            render={({ field }) => (
              <Select
                {...field}
                options={providers.map((provider) => ({
                  value: provider,
                  label: provider,
                }))}
              />
            )}
          />
        </Form.Item>
        <Form.Item
          label="名称"
          validateStatus={errors.key_name ? 'error' : undefined}
          help={errors.key_name?.message}
        >
          <Controller
            name="key_name"
            control={control}
            render={({ field }) => <Input {...field} />}
          />
        </Form.Item>
        <Form.Item
          label="密钥"
          validateStatus={errors.api_key ? 'error' : undefined}
          help={errors.api_key?.message}
        >
          <Controller
            name="api_key"
            control={control}
            render={({ field }) => <Input.Password {...field} />}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting}>
          添加
        </Button>
      </Form>
      {groups.length === 0 ? <p>还没有 API 密钥</p> : null}
      {groups.map((group) => (
        <section key={group.provider}>
          <h2>{group.label}</h2>
          <ul>
            {group.keys.map((item) => (
              <KeyRow key={item.id} item={item} />
            ))}
          </ul>
        </section>
      ))}
    </section>
  )
}
