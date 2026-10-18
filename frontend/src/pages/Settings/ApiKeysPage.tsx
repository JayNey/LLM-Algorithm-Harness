import { Alert, Button, Form, Input, Modal, Select } from 'antd'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import {
  groupApiKeys,
  lastUsedLabel,
  providers,
  readApiKeys,
  rejectApiKey,
  renamePayload,
  validateKeyName,
  verifyStatusText,
  type ApiKeyRecord,
  type Provider,
} from '@/account/apiKeys.ts'
import { formatUnixSeconds } from '@/account/profile.ts'
import { ApiClientError } from '@/auth/http.ts'
import { useAuthStore } from '@/store/auth.ts'

interface AddInput {
  provider: Provider
  key_name: string
  api_key: string
}

function KeyRow({
  item,
  load,
  verifying,
  markVerifying,
  setNotice,
}: {
  item: ApiKeyRecord
  load: () => Promise<void>
  verifying: boolean
  markVerifying: (id: string, active: boolean) => void
  setNotice: (message: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(item.key_name)
  const [nameError, setNameError] = useState('')
  const [saving, setSaving] = useState(false)

  async function saveName() {
    const invalid = validateKeyName(name)
    if (invalid) {
      setNameError(invalid)
      return
    }
    setNameError('')
    setSaving(true)
    try {
      await useAuthStore
        .getState()
        .httpClient()
        .patch('/api-keys/' + item.id, renamePayload(name))
      await load()
      setEditing(false)
    } catch (error) {
      setNameError(
        error instanceof ApiClientError && error.status === 429
          ? '请求过于频繁，请稍后再试'
          : '服务暂时不可用',
      )
    } finally {
      setSaving(false)
    }
  }

  function confirmDelete() {
    Modal.confirm({
      title: '删除这条密钥？',
      okText: '删除',
      cancelText: '取消',
      onOk: async () => {
        await useAuthStore
          .getState()
          .httpClient()
          .delete('/api-keys/' + item.id)
        await load()
      },
    })
  }

  async function verify() {
    markVerifying(item.id, true)
    try {
      const result: unknown = await useAuthStore
        .getState()
        .httpClient()
        .post('/api-keys/' + item.id + '/verify')
      const ok =
        typeof result === 'object' &&
        result !== null &&
        'ok' in result &&
        result.ok === true
      setNotice(verifyStatusText(ok))
      await load()
    } catch (error) {
      setNotice(
        error instanceof ApiClientError && error.status === 429
          ? '请求过于频繁，请稍后再试'
          : '服务暂时不可用',
      )
    } finally {
      markVerifying(item.id, false)
    }
  }

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
      {editing ? (
        <div>
          <Input
            value={name}
            onChange={(event) => {
              setName(event.target.value)
            }}
          />
          {nameError ? <p>{nameError}</p> : null}
          <Button
            type="primary"
            loading={saving}
            onClick={() => {
              void saveName()
            }}
          >
            保存
          </Button>
        </div>
      ) : (
        <Button
          onClick={() => {
            setName(item.key_name)
            setNameError('')
            setEditing(true)
          }}
        >
          改名
        </Button>
      )}
      <Button danger onClick={confirmDelete}>
        删除
      </Button>
      <Button
        loading={verifying}
        onClick={() => {
          void verify()
        }}
      >
        验证
      </Button>
    </li>
  )
}

export default function ApiKeysPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [keys, setKeys] = useState<ApiKeyRecord[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [formMessage, setFormMessage] = useState('')
  const [notice, setNotice] = useState('')
  const [verifyingIds, setVerifyingIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  )

  function markVerifying(id: string, active: boolean) {
    setVerifyingIds((current) => {
      const next = new Set(current)
      if (active) next.add(id)
      else next.delete(id)
      return next
    })
  }
  const {
    control,
    handleSubmit,
    reset,
    setError: setFieldError,
    clearErrors,
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
    clearErrors()
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
      {notice ? (
        <Alert
          type={notice === '验证成功' ? 'success' : 'error'}
          message={notice}
          showIcon
        />
      ) : null}
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
              <KeyRow
                key={item.id}
                item={item}
                load={load}
                verifying={verifyingIds.has(item.id)}
                markVerifying={markVerifying}
                setNotice={setNotice}
              />
            ))}
          </ul>
        </section>
      ))}
    </section>
  )
}
