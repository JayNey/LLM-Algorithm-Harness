import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Form, Input, Modal, Select } from 'antd'
import { useState } from 'react'
import type { AxiosInstance } from 'axios'
import { Controller, useForm } from 'react-hook-form'
import {
  groupApiKeys,
  lastUsedLabel,
  providers,
  readApiKeys,
  rejectApiKey,
  renamePayload,
  requestFailureText,
  validateKeyName,
  verifyStatusText,
  type ApiKeyRecord,
  type Provider,
} from '@/account/apiKeys.ts'
import { formatUnixSeconds } from '@/account/profile.ts'
import { ApiClientError } from '@/auth/http.ts'
import { escapeHtml } from '@/auth/text.ts'
import { useResource } from '@/hooks/useResource.ts'
import { useAuthStore } from '@/store/auth.ts'

interface AddInput {
  provider: Provider
  key_name: string
  api_key: string
}

function failureText(error: unknown): string {
  return requestFailureText(
    error instanceof ApiClientError ? error.status : undefined,
  )
}

type KeyNotice = { type: 'success' | 'error'; text: string }

async function loadKeys(signal: AbortSignal) {
  const http = useAuthStore.getState().httpClient() as AxiosInstance
  const keys = readApiKeys(
    await http.get<unknown, unknown>('/api-keys', { signal, timeout: 10_000 }),
  )
  if (!keys) throw new Error('密钥列表响应无效，请重试')
  return keys
}

function KeyRow({
  item,
  refresh,
  verifying,
  markVerifying,
  setNotice,
}: {
  item: ApiKeyRecord
  refresh: () => void
  verifying: boolean
  markVerifying: (id: string, active: boolean) => void
  setNotice: (notice: KeyNotice) => void
}) {
  useTranslation()

  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(item.key_name)
  const [nameError, setNameError] = useState('')
  const [saving, setSaving] = useState(false)
  const [modal, modalHolder] = Modal.useModal()

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
    } catch (error) {
      setNameError(failureText(error))
      return
    } finally {
      setSaving(false)
    }
    setEditing(false)
    setNotice({ type: 'success', text: '密钥已改名' })
    refresh()
  }

  function confirmDelete() {
    modal.confirm({
      title: t('删除这条密钥？'),
      okText: t('删除'),
      cancelText: t('取消'),
      onOk: async () => {
        try {
          await useAuthStore
            .getState()
            .httpClient()
            .delete('/api-keys/' + item.id)
        } catch (error) {
          setNotice({ type: 'error', text: failureText(error) })
          return
        }
        setNotice({ type: 'success', text: '密钥已删除' })
        refresh()
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
      setNotice({ type: ok ? 'success' : 'error', text: verifyStatusText(ok) })
    } catch (error) {
      setNotice({ type: 'error', text: failureText(error) })
      return
    } finally {
      markVerifying(item.id, false)
    }
    refresh()
  }

  return (
    <li>
      {modalHolder}
      <p>{escapeHtml(item.key_name)}</p>
      {item.masked_preview ? <p>{escapeHtml(item.masked_preview)}</p> : null}
      <p>{item.provider}</p>
      <p>
        {t('创建时间：')}
        {formatUnixSeconds(item.created_at)}
      </p>
      <p>{item.verified ? t('已验证') : t('未验证')}</p>
      <p>
        {t('使用次数：')}
        {item.usage_count}
      </p>
      <p>
        {item.last_used_at === null
          ? t(lastUsedLabel(null))
          : t('最后使用：{{value1}}', {
              value1: formatUnixSeconds(item.last_used_at),
            })}
      </p>
      {editing ? (
        <div>
          <Input
            value={name}
            onChange={(event) => {
              setName(event.target.value)
            }}
          />
          {nameError ? <p>{t(nameError)}</p> : null}
          <Button
            type="primary"
            loading={saving}
            onClick={() => {
              void saveName()
            }}
          >
            {t('保存')}
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
          {t('改名')}
        </Button>
      )}
      <Button danger onClick={confirmDelete}>
        {t('删除')}
      </Button>
      <Button
        loading={verifying}
        onClick={() => {
          void verify()
        }}
      >
        {t('验证')}
      </Button>
    </li>
  )
}

export default function ApiKeysPage() {
  useTranslation()

  const keys = useResource(loadKeys)
  const [submitting, setSubmitting] = useState(false)
  const [formMessage, setFormMessage] = useState('')
  const [notice, setNotice] = useState<KeyNotice | null>(null)
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
    } catch (error) {
      setFormMessage(failureText(error))
      return
    } finally {
      setSubmitting(false)
    }
    reset({ provider: 'openai', key_name: '', api_key: '' })
    setNotice({ type: 'success', text: '密钥已添加' })
    keys.retry()
  }

  const header = (
    <>
      <h1>{t('API 密钥')}</h1>
      {notice ? (
        <Alert
          className="mb-2"
          type={notice.type}
          title={t(notice.text)}
          showIcon
        />
      ) : null}
    </>
  )
  if (keys.loading || keys.error) {
    return (
      <section>
        {header}
        {keys.loading ? (
          <p role="status">{t('正在加载密钥列表')}</p>
        ) : (
          <Alert
            type="error"
            title={t('密钥列表加载失败')}
            showIcon
            action={<Button onClick={keys.retry}>{t('重试')}</Button>}
          />
        )}
      </section>
    )
  }

  const groups = groupApiKeys(keys.data ?? [])
  return (
    <section>
      {header}
      <p>{t('密钥保存后不再显示')}</p>
      {formMessage ? (
        <Alert type="error" message={t(formMessage)} showIcon />
      ) : null}
      <Form
        layout="vertical"
        noValidate
        onFinish={() => {
          void handleSubmit(onSubmit)()
        }}
      >
        <Form.Item label={t('提供商')}>
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
          label={t('名称')}
          validateStatus={errors.key_name ? 'error' : undefined}
          help={t(errors.key_name?.message)}
        >
          <Controller
            name="key_name"
            control={control}
            render={({ field }) => <Input {...field} />}
          />
        </Form.Item>
        <Form.Item
          label={t('密钥')}
          validateStatus={errors.api_key ? 'error' : undefined}
          help={t(errors.api_key?.message)}
        >
          <Controller
            name="api_key"
            control={control}
            render={({ field }) => <Input.Password {...field} />}
          />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting}>
          {t('添加')}
        </Button>
      </Form>
      {groups.length === 0 ? <p>{t('还没有 API 密钥')}</p> : null}
      {groups.map((group) => (
        <section key={group.provider}>
          <h2>{group.label}</h2>
          <ul>
            {group.keys.map((item) => (
              <KeyRow
                key={item.id}
                item={item}
                refresh={keys.retry}
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
