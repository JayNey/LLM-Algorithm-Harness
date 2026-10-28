import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Button, Input, Select, Skeleton } from 'antd'
import { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { readApiKeys } from '@/account/apiKeys.ts'
import { ApiClientError } from '@/auth/http.ts'
import { useAuthStore } from '@/store/auth.ts'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { createPayload } from '@/abtests/validation.ts'
import { useABTestSession } from '@/abtests/session.tsx'
import type { ABTestDraft, DraftErrors } from '@/abtests/types.ts'
import { validateABTestDraft } from '@/abtests/validation.ts'
import type { AxiosInstance } from 'axios'
import {
  ModelNameField,
  StrategyNameField,
} from '@/evaluations/optionFields.tsx'
import { useResource } from '@/hooks/useResource.ts'

function VariantFields({
  index,
  role,
  draft,
  onChange,
  disabled,
}: {
  index: number
  role: string
  draft: ABTestDraft
  onChange: (patch: Partial<ABTestDraft>) => void
  disabled: boolean
}) {
  useTranslation()

  const variant = draft.variants[index]
  function update(patch: Partial<ABTestDraft['variants'][number]>) {
    onChange({
      variants: draft.variants.map((item, at) =>
        at === index ? { ...item, ...patch } : item,
      ),
    })
  }
  return (
    <fieldset>
      <legend>
        {role}
        {t('变体')}
      </legend>
      <label>
        {t('变体 ID')}
        <Input
          aria-label={t('{{value1}}变体 ID', { value1: role })}
          value={variant.id}
          placeholder={role === t('基线') ? 'baseline' : 'treatment'}
          onChange={(event) => update({ id: event.target.value })}
          disabled={disabled}
        />
      </label>
      <label>
        {t('描述（可选）')}
        <Input
          aria-label={t('{{value1}}变体描述', { value1: role })}
          value={variant.description}
          onChange={(event) => update({ description: event.target.value })}
          disabled={disabled}
        />
      </label>
      <label>
        {t('System Prompt（可选）')}
        <Input.TextArea
          aria-label={t('{{value1}}变体系统提示词', { value1: role })}
          rows={2}
          value={variant.system_prompt}
          onChange={(event) => update({ system_prompt: event.target.value })}
          disabled={disabled}
        />
      </label>
      <label>
        {t('前缀（可选）')}
        <Input
          aria-label={t('{{value1}}变体前缀', { value1: role })}
          value={variant.prefix}
          onChange={(event) => update({ prefix: event.target.value })}
          disabled={disabled}
        />
      </label>
      <label>
        {t('后缀（可选）')}
        <Input
          aria-label={t('{{value1}}变体后缀', { value1: role })}
          value={variant.suffix}
          onChange={(event) => update({ suffix: event.target.value })}
          disabled={disabled}
        />
      </label>
    </fieldset>
  )
}

export default function CreateABTestPage() {
  useTranslation()

  const { client } = useABTestSession()
  const navigate = useNavigate()
  const [draft, setDraft] = useState<ABTestDraft>({
    name: '',
    dataset_path: '',
    api_key_id: '',
    model: '',
    model_temperature: '',
    strategy: 'direct',
    strategy_max_iterations: '',
    seed: '42',
    max_workers: '4',
    variants: [
      {
        id: 'baseline',
        description: '',
        system_prompt: '',
        prefix: '',
        suffix: '',
      },
      {
        id: 'treatment',
        description: '',
        system_prompt: '',
        prefix: '',
        suffix: '',
      },
    ],
  })
  const [errors, setErrors] = useState<DraftErrors>({})
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const keys = useResource(
    useCallback(async (signal: AbortSignal) => {
      const http = useAuthStore.getState().httpClient() as AxiosInstance
      const data = readApiKeys(
        await http.get<unknown, unknown>('/api-keys', {
          signal,
          timeout: 10_000,
        }),
      )
      if (!data) throw new ApiClientError('密钥列表响应无效，请重试')
      return data
    }, []),
  )
  function update(patch: Partial<ABTestDraft>) {
    setDraft((previous) => ({ ...previous, ...patch }))
  }
  async function submit() {
    const nextErrors = validateABTestDraft(draft)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    setBusy(true)
    setActionError(null)
    const payload = createPayload(draft)
    try {
      const created = await client.create(payload)
      void navigate(`/ab-tests/${encodeURIComponent(created.id)}`, {
        replace: true,
      })
    } catch (cause: unknown) {
      setActionError(
        cause instanceof Error ? cause.message : '创建失败，请重试',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('创建 A/B 测试')}</h1>
          <p>{t('同一模型与策略下，对比两个提示词变体的通过率差异。')}</p>
        </div>
        <Link className="evaluation-create-link" to="/ab-tests">
          {t('返回列表')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        {actionError && <ExperimentFeedback message={t(actionError)} />}
        {!keys.data ? (
          keys.error ? (
            <ExperimentFeedback message={t(keys.error)} retry={keys.retry} />
          ) : (
            <Skeleton active paragraph={{ rows: 6 }} />
          )
        ) : (
          <>
            <label>
              {t('测试名称（可选）')}
              <Input
                aria-label={t('A/B 测试名称')}
                value={draft.name}
                maxLength={200}
                onChange={(event) => update({ name: event.target.value })}
              />
              {errors.name && <small role="alert">{t(errors.name)}</small>}
            </label>
            <label>
              {t('数据集路径')}
              <Input
                aria-label={t('A/B 数据集路径')}
                value={draft.dataset_path}
                placeholder="datasets/demo.json"
                onChange={(event) =>
                  update({ dataset_path: event.target.value })
                }
              />
              {errors.dataset_path && (
                <small role="alert">{t(errors.dataset_path)}</small>
              )}
            </label>
            <label>
              API Key
              <Select
                aria-label={t('A/B 密钥')}
                value={draft.api_key_id || undefined}
                placeholder={t('选择可用密钥')}
                options={keys.data.map((key) => ({
                  value: key.id,
                  label: key.key_name || key.id,
                }))}
                onChange={(value: string) => update({ api_key_id: value })}
              />
              {errors.api_key_id && (
                <small role="alert">{t(errors.api_key_id)}</small>
              )}
            </label>
            <label>
              {t('模型')}
              <ModelNameField
                ariaLabel={t('A/B 模型')}
                value={draft.model}
                apiKeyId={draft.api_key_id}
                onChange={(value) => update({ model: value })}
              />
              {errors.model && <small role="alert">{t(errors.model)}</small>}
            </label>
            <label>
              {t('模型温度（可选，0–2）')}
              <Input
                aria-label={t('A/B 模型温度')}
                value={draft.model_temperature}
                onChange={(event) =>
                  update({ model_temperature: event.target.value })
                }
              />
              {errors.model && <small role="alert">{t(errors.model)}</small>}
            </label>
            <label>
              {t('策略')}
              <StrategyNameField
                ariaLabel={t('A/B 策略')}
                value={draft.strategy}
                onChange={(value) => update({ strategy: value })}
              />
              {errors.strategy && (
                <small role="alert">{t(errors.strategy)}</small>
              )}
            </label>
            <label>
              {t('策略最大迭代（可选，1–10）')}
              <Input
                aria-label={t('A/B 策略最大迭代')}
                value={draft.strategy_max_iterations}
                onChange={(event) =>
                  update({ strategy_max_iterations: event.target.value })
                }
              />
              {errors.strategy && (
                <small role="alert">{t(errors.strategy)}</small>
              )}
            </label>
            <label>
              {t('随机种子')}
              <Input
                aria-label={t('A/B 随机种子')}
                value={draft.seed}
                onChange={(event) => update({ seed: event.target.value })}
              />
              {errors.seed && <small role="alert">{t(errors.seed)}</small>}
            </label>
            <label>
              {t('并行数（1–20）')}
              <Input
                aria-label={t('A/B 并行数')}
                value={draft.max_workers}
                onChange={(event) =>
                  update({ max_workers: event.target.value })
                }
              />
              {errors.max_workers && (
                <small role="alert">{t(errors.max_workers)}</small>
              )}
            </label>
            <VariantFields
              index={0}
              role={t('基线')}
              draft={draft}
              onChange={update}
              disabled={busy}
            />
            <VariantFields
              index={1}
              role={t('实验')}
              draft={draft}
              onChange={update}
              disabled={busy}
            />
            {errors.variants && (
              <small role="alert">{t(errors.variants)}</small>
            )}
            <Button
              type="primary"
              aria-label={t('提交 A/B 测试')}
              disabled={busy}
              onClick={() => void submit()}
            >
              {busy ? t('创建中…') : t('创建 A/B 测试')}
            </Button>
          </>
        )}
      </div>
    </section>
  )
}
