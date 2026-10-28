import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Input, Select, Skeleton } from 'antd'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useStore } from 'zustand'
import { readApiKeys } from '@/account/apiKeys.ts'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import {
  budgetKindLabels,
  executionLabels,
} from '@/experiments/presentation.ts'
import { useExperimentSession } from '@/experiments/session.tsx'
import type { DraftErrors, ExperimentDraft } from '@/experiments/types.ts'
import { validateExperimentDraft } from '@/experiments/validation.ts'
import { useAuthStore } from '@/store/auth.ts'
import type { AxiosInstance } from 'axios'
import { useCallback } from 'react'
import {
  ModelNameField,
  StrategyNameField,
} from '@/evaluations/optionFields.tsx'
import { effectiveApiKey } from '@/evaluations/optionCatalog.ts'
import { useResource } from '@/hooks/useResource.ts'
import '@/evaluations/workflow.css'

export default function CreateExperimentPage() {
  useTranslation()

  const { creationStore } = useExperimentSession()
  const { draft, phase, error, setDraft, submit, reset } =
    useStore(creationStore)
  const navigate = useNavigate()
  const [errors, setErrors] = useState<DraftErrors>({})
  const keys = useResource(
    useCallback(async (signal: AbortSignal) => {
      const http = useAuthStore.getState().httpClient() as AxiosInstance
      return readApiKeys(
        await http.get<unknown, unknown>('/api-keys', {
          signal,
          timeout: 10_000,
        }),
      )
    }, []),
  )
  const editing = phase === 'editing'
  const creating = phase === 'creating'
  const created = phase === 'created'
  function update(patch: Partial<ExperimentDraft>) {
    setDraft(patch)
  }
  function updateModel(
    index: number,
    patch: Partial<ExperimentDraft['models'][number]>,
  ) {
    update({
      models: draft.models.map((model, at) =>
        at === index ? { ...model, ...patch } : model,
      ),
    })
  }
  function updateStrategy(
    index: number,
    patch: Partial<ExperimentDraft['strategies'][number]>,
  ) {
    update({
      strategies: draft.strategies.map((strategy, at) =>
        at === index ? { ...strategy, ...patch } : strategy,
      ),
    })
  }
  function create() {
    const nextErrors = validateExperimentDraft(draft)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    void submit()
  }
  if (created) {
    return (
      <section className="evaluation-workflow">
        <div className="panel evaluation-panel">
          <Alert
            type="success"
            showIcon
            message={t('实验已创建')}
            description={
              <p>
                {t('实验编号 ')}
                {draft.name || creationStore.getState().experimentId}。
                <Link
                  to={`/experiments/${encodeURIComponent(creationStore.getState().experimentId ?? '')}`}
                >
                  {t('前往详情页启动')}
                </Link>
              </p>
            }
          />
        </div>
      </section>
    )
  }
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('创建实验')}</h1>
          <p>{t('固定预算对比实验：多模型 × 多策略，按预算重复执行。')}</p>
        </div>
        <Link className="evaluation-create-link" to="/experiments">
          {t('返回列表')}
        </Link>
      </header>
      <div className="panel evaluation-panel">
        {!keys.data ? (
          keys.error ? (
            <ExperimentFeedback message={t(keys.error)} retry={keys.retry} />
          ) : (
            <Skeleton active paragraph={{ rows: 6 }} />
          )
        ) : (
          <>
            {error && <ExperimentFeedback message={t(error.message)} />}
            <label>
              {t('实验名称（可选）')}
              <Input
                aria-label={t('实验名称')}
                value={draft.name}
                maxLength={200}
                onChange={(event) => update({ name: event.target.value })}
                disabled={!editing}
              />
            </label>
            <label>
              {t('数据集路径（DATA_ROOT 下的相对路径）')}
              <Input
                aria-label={t('数据集路径')}
                value={draft.dataset_path}
                placeholder="datasets/demo.json"
                onChange={(event) =>
                  update({ dataset_path: event.target.value })
                }
                disabled={!editing}
              />
              {errors.dataset_path && (
                <small role="alert">{t(errors.dataset_path)}</small>
              )}
            </label>
            <label>
              API Key
              <Select
                aria-label={t('实验 API Key')}
                value={draft.api_key_id || undefined}
                placeholder={t('选择可用密钥')}
                options={keys.data.map((key) => ({
                  value: key.id,
                  label: key.key_name || key.id,
                }))}
                onChange={(value: string) => update({ api_key_id: value })}
                disabled={!editing}
              />
              {errors.api_key_id && (
                <small role="alert">{t(errors.api_key_id)}</small>
              )}
            </label>

            <fieldset>
              <legend>{t('模型（至少一个）')}</legend>
              {draft.models.map((model, index) => (
                <div key={index} className="evaluation-section-heading">
                  <ModelNameField
                    ariaLabel={t('模型 {{value1}} 名称', {
                      value1: index + 1,
                    })}
                    value={model.model}
                    apiKeyId={effectiveApiKey(
                      model.api_key_id,
                      draft.api_key_id,
                    )}
                    onChange={(value) => updateModel(index, { model: value })}
                    disabled={!editing}
                  />
                  <Input
                    aria-label={t('模型 {{value1}} 温度', {
                      value1: index + 1,
                    })}
                    placeholder={t('温度 0–2（可选）')}
                    value={model.temperature}
                    onChange={(event) =>
                      updateModel(index, { temperature: event.target.value })
                    }
                    disabled={!editing}
                  />
                  <Select
                    aria-label={t('模型 {{value1}} 专用密钥', {
                      value1: index + 1,
                    })}
                    placeholder={t('专用密钥 ID（可选）')}
                    allowClear
                    value={model.api_key_id || undefined}
                    options={(keys.data ?? []).map((key) => ({
                      value: key.id,
                      label: key.key_name || key.id,
                    }))}
                    onChange={(value: string | undefined) =>
                      updateModel(index, { api_key_id: value ?? '' })
                    }
                    disabled={!editing}
                  />
                  {draft.models.length > 1 && editing && (
                    <Button
                      aria-label={t('移除模型 {{value1}}', {
                        value1: index + 1,
                      })}
                      onClick={() =>
                        update({
                          models: draft.models.filter((_, at) => at !== index),
                        })
                      }
                    >
                      {t('移除')}
                    </Button>
                  )}
                </div>
              ))}
              {editing && (
                <Button
                  aria-label={t('添加模型')}
                  onClick={() =>
                    update({
                      models: [
                        ...draft.models,
                        { model: '', temperature: '', api_key_id: '' },
                      ],
                    })
                  }
                >
                  {t('添加模型')}
                </Button>
              )}
              {errors.models && <small role="alert">{t(errors.models)}</small>}
            </fieldset>

            <fieldset>
              <legend>{t('策略（至少一个）')}</legend>
              {draft.strategies.map((strategy, index) => (
                <div key={index} className="evaluation-section-heading">
                  <StrategyNameField
                    ariaLabel={t('策略 {{value1}} 名称', {
                      value1: index + 1,
                    })}
                    value={strategy.name}
                    onChange={(value) => updateStrategy(index, { name: value })}
                    disabled={!editing}
                  />
                  <Input
                    aria-label={t('策略 {{value1}} 最大迭代', {
                      value1: index + 1,
                    })}
                    placeholder={t('最大迭代 1–10（可选）')}
                    value={strategy.max_iterations}
                    onChange={(event) =>
                      updateStrategy(index, {
                        max_iterations: event.target.value,
                      })
                    }
                    disabled={!editing}
                  />
                  <Input
                    aria-label={t('策略 {{value1}} 温度', {
                      value1: index + 1,
                    })}
                    placeholder={t('温度 0–2（可选）')}
                    value={strategy.temperature}
                    onChange={(event) =>
                      updateStrategy(index, { temperature: event.target.value })
                    }
                    disabled={!editing}
                  />
                  {draft.strategies.length > 1 && editing && (
                    <Button
                      aria-label={t('移除策略 {{value1}}', {
                        value1: index + 1,
                      })}
                      onClick={() =>
                        update({
                          strategies: draft.strategies.filter(
                            (_, at) => at !== index,
                          ),
                        })
                      }
                    >
                      {t('移除')}
                    </Button>
                  )}
                </div>
              ))}
              {editing && (
                <Button
                  aria-label={t('添加策略')}
                  onClick={() =>
                    update({
                      strategies: [
                        ...draft.strategies,
                        { name: '', max_iterations: '', temperature: '' },
                      ],
                    })
                  }
                >
                  {t('添加策略')}
                </Button>
              )}
              {errors.strategies && (
                <small role="alert">{t(errors.strategies)}</small>
              )}
            </fieldset>

            <label>
              {t('重复次数')}
              <Input
                aria-label={t('实验重复次数')}
                value={draft.repeats}
                onChange={(event) => update({ repeats: event.target.value })}
                disabled={!editing}
              />
              {errors.repeats && (
                <small role="alert">{t(errors.repeats)}</small>
              )}
            </label>
            <label>
              {t('执行模式')}
              <Select
                aria-label={t('实验执行模式')}
                value={draft.execution}
                options={Object.entries(executionLabels).map(
                  ([value, label]) => ({
                    value,
                    label,
                  }),
                )}
                onChange={(value: 'serial' | 'parallel') =>
                  update({ execution: value })
                }
                disabled={!editing}
              />
            </label>
            {draft.execution === 'parallel' && (
              <label>
                {t('并行数')}
                <Input
                  aria-label={t('实验并行数')}
                  value={draft.max_workers}
                  onChange={(event) =>
                    update({ max_workers: event.target.value })
                  }
                  disabled={!editing}
                />
                {errors.max_workers && (
                  <small role="alert">{t(errors.max_workers)}</small>
                )}
              </label>
            )}
            <label>
              {t('预算类型')}
              <Select
                aria-label={t('实验预算类型')}
                value={draft.budget_kind}
                options={Object.entries(budgetKindLabels).map(
                  ([value, label]) => ({
                    value,
                    label,
                  }),
                )}
                onChange={(value: ExperimentDraft['budget_kind']) =>
                  update({ budget_kind: value })
                }
                disabled={!editing}
              />
            </label>
            {draft.budget_kind !== 'none' && (
              <label>
                {t('预算限制值（')}
                {budgetKindLabels[draft.budget_kind]}）
                <Input
                  aria-label={t('实验预算限制值')}
                  value={draft.budget_value}
                  onChange={(event) =>
                    update({ budget_value: event.target.value })
                  }
                  disabled={!editing}
                />
                {errors.budget_value && (
                  <small role="alert">{t(errors.budget_value)}</small>
                )}
              </label>
            )}

            {phase === 'create-unknown' && (
              <>
                <Alert
                  role="alert"
                  type="warning"
                  message={t(
                    '创建结果未知，请勿重复提交；可前往列表确认，或重置表单后重新创建。',
                  )}
                />
                <Button
                  aria-label={t('重置未知创建')}
                  onClick={() => {
                    setErrors({})
                    reset(useAuthStore.getState().session?.marker ?? null)
                  }}
                >
                  {t('重置表单')}
                </Button>
              </>
            )}
            <div className="evaluation-section-heading">
              <Button
                type="primary"
                aria-label={t('提交实验')}
                disabled={!editing || creating}
                onClick={create}
              >
                {creating ? t('创建中…') : t('创建实验')}
              </Button>
              {editing && (
                <Button
                  aria-label={t('重置实验草稿')}
                  onClick={() => {
                    setErrors({})
                    reset(useAuthStore.getState().session?.marker ?? null)
                  }}
                >
                  {t('重置')}
                </Button>
              )}
              {!editing && (
                <Button
                  aria-label={t('返回编辑实验草稿')}
                  onClick={() => navigate('/experiments/new')}
                >
                  {t('返回编辑')}
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  )
}
