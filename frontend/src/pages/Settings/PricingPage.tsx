import { useTranslation } from 'react-i18next'
import { currentLanguage, t } from '../../i18n/core.ts'
import { Alert, Button, Drawer, Input, Skeleton } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { usePricingSession } from '@/pricing/session.tsx'
import type { PricingCatalog, PricingVersion } from '@/pricing/types.ts'
import { validateOverrideInput } from '@/pricing/client.ts'

const SOURCE_LABELS: Record<string, string> = {
  get builtin() {
    return t('内置')
  },
  get custom_file() {
    return t('自定义文件')
  },
  get override() {
    return t('覆盖')
  },
}

function useHistoryDrawer(
  client: ReturnType<typeof usePricingSession>['client'],
) {
  const [model, setModel] = useState<string | null>(null)
  const [versions, setVersions] = useState<PricingVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(
    (target: string) => {
      const controller = new AbortController()
      void client.history(target, controller.signal).then(
        (data) => {
          if (!controller.signal.aborted) {
            setVersions(data)
            setError(null)
          }
        },
        (cause: unknown) => {
          if (!controller.signal.aborted)
            setError(cause instanceof Error ? cause.message : '加载失败')
        },
      )
      return () => controller.abort()
    },
    [client],
  )
  useEffect(() => {
    if (model === null) return
    // 换模型时在异步回调链里复位（不在 effect 体内同步 setState）
    const controller = new AbortController()
    queueMicrotask(() => {
      if (!controller.signal.aborted) setVersions(null)
    })
    const stop = reload(model)
    return () => {
      controller.abort()
      stop()
    }
  }, [model, reload])
  const drawer = (
    <Drawer
      title={model ? t('{{value1}} · 定价历史', { value1: model }) : ''}
      open={model !== null}
      onClose={() => setModel(null)}
      width={480}
    >
      {error ? (
        <ExperimentFeedback
          message={t(error)}
          retry={() => model && reload(model)}
        />
      ) : versions === null ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : versions.length ? (
        <table className="evaluation-list-table" aria-label={t('定价历史')}>
          <thead>
            <tr>
              {[t('输入价/1k'), t('输出价/1k'), t('创建者'), t('时间')].map(
                (name) => (
                  <th key={name} scope="col">
                    {name}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {versions.map((version, index) => (
              <tr key={index}>
                <td>${version.prompt_per_1k}</td>
                <td>${version.completion_per_1k}</td>
                <td>{version.created_by}</td>
                <td>
                  {new Date(version.created_at).toLocaleString(
                    currentLanguage(),
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p role="status">{t('该模型没有自定义定价历史。')}</p>
      )}
    </Drawer>
  )
  return { open: setModel, drawer }
}

export default function PricingPage() {
  useTranslation()

  const { client } = usePricingSession()
  const [catalog, setCatalog] = useState<PricingCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    modelId: '',
    prompt_per_1k: '',
    completion_per_1k: '',
  })
  const [formErrors, setFormErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const history = useHistoryDrawer(client)

  const reload = useCallback(() => {
    const controller = new AbortController()
    void client.catalog(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) {
          setCatalog(data)
          setError(null)
        }
      },
      (cause: unknown) => {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : '加载失败')
      },
    )
    return () => controller.abort()
  }, [client])

  useEffect(() => reload(), [reload])

  async function submit() {
    if (busy) return
    const errors = validateOverrideInput(form)
    setFormErrors(errors)
    if (Object.keys(errors).length) return
    setBusy(true)
    setMessage(null)
    try {
      await client.addOverride({
        modelId: form.modelId.trim(),
        prompt_per_1k: Number(form.prompt_per_1k),
        completion_per_1k: Number(form.completion_per_1k),
      })
      setMessage('自定义定价已追加（最新版本生效）。')
      setForm({ modelId: '', prompt_per_1k: '', completion_per_1k: '' })
      reload()
    } catch (cause: unknown) {
      setMessage(cause instanceof Error ? cause.message : '追加失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  const entries = catalog
    ? Object.entries(catalog.models).sort(([a], [b]) => a.localeCompare(b))
    : []
  return (
    <section className="mx-auto w-full max-w-3xl">
      <h1 className="mb-2 text-xl font-semibold">{t('定价管理')}</h1>
      <p className="mb-6 text-neutral-600 dark:text-neutral-400">
        {t(
          '查看三源合并的模型定价（USD / 1k tokens）；自定义定价为追加式，最新版本覆盖生效。',
        )}
      </p>
      {message && (
        <Alert message={t(message)} type="info" showIcon className="mb-4" />
      )}
      {error ? (
        <ExperimentFeedback message={t(error)} retry={reload} />
      ) : catalog === null ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : entries.length ? (
        <table className="evaluation-list-table" aria-label={t('定价目录')}>
          <thead>
            <tr>
              {[
                t('模型'),
                t('输入价/1k'),
                t('输出价/1k'),
                t('来源'),
                t('操作'),
              ].map((name) => (
                <th key={name} scope="col">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map(([model, entry]) => (
              <tr key={model}>
                <td>{model}</td>
                <td>${entry.prompt_per_1k}</td>
                <td>${entry.completion_per_1k}</td>
                <td>{SOURCE_LABELS[entry.source] ?? entry.source}</td>
                <td>
                  <Button size="small" onClick={() => history.open(model)}>
                    {t('历史')}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p role="status">{t('目录为空。')}</p>
      )}
      <fieldset className="mt-6">
        <legend>{t('追加自定义定价')}</legend>
        <div className="evaluation-section-heading">
          <label>
            {t('模型 ID')}
            <Input
              aria-label={t('模型 ID')}
              value={form.modelId}
              placeholder={t('如 gpt-4o-mini')}
              onChange={(event) =>
                setForm({ ...form, modelId: event.target.value })
              }
            />
            {formErrors.modelId && (
              <small role="alert">{t(formErrors.modelId)}</small>
            )}
          </label>
          <label>
            {t('输入价 / 1k tokens')}
            <Input
              aria-label={t('输入价')}
              value={form.prompt_per_1k}
              placeholder={t('如 0.15')}
              onChange={(event) =>
                setForm({ ...form, prompt_per_1k: event.target.value })
              }
            />
            {formErrors.prompt_per_1k && (
              <small role="alert">{t(formErrors.prompt_per_1k)}</small>
            )}
          </label>
          <label>
            {t('输出价 / 1k tokens')}
            <Input
              aria-label={t('输出价')}
              value={form.completion_per_1k}
              placeholder={t('如 0.6')}
              onChange={(event) =>
                setForm({ ...form, completion_per_1k: event.target.value })
              }
            />
            {formErrors.completion_per_1k && (
              <small role="alert">{t(formErrors.completion_per_1k)}</small>
            )}
          </label>
          <Button
            type="primary"
            aria-label={t('追加定价')}
            disabled={busy}
            onClick={() => void submit()}
          >
            {busy ? t('追加中…') : t('追加')}
          </Button>
        </div>
      </fieldset>
      {history.drawer}
      <p className="mt-6">
        <Link to="/settings">{t('返回设置')}</Link>
      </p>
    </section>
  )
}
