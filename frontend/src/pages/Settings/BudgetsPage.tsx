import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Input, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { useBudgetSession } from '@/budgets/session.tsx'
import type { AlertChannel, AlertRule, BudgetUsage } from '@/budgets/types.ts'
import { validateAlertInput, validateBudgetInput } from '@/budgets/client.ts'

const CHANNEL_OPTIONS: { value: AlertChannel; label: string }[] = [
  {
    value: 'log',
    get label() {
      return t('日志（log）')
    },
  },
  { value: 'webhook', label: 'Webhook' },
  { value: 'slack', label: 'Slack' },
  {
    value: 'smtp',
    get label() {
      return t('邮件（SMTP）')
    },
  },
]

function formatUsd(value: number | null): string {
  return value === null ? '—' : `$${value.toFixed(2)}`
}

function useResource<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{
    load: typeof load
    attempt: number
    data?: T
    error?: string
  }>()
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ load, attempt, data })
      },
      (error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            load,
            attempt,
            error: error instanceof Error ? error.message : '加载失败，请重试',
          })
      },
    )
    return () => controller.abort()
  }, [load, attempt])
  const current = state?.load === load && state.attempt === attempt
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: !current,
    retry: () => setAttempt((value) => value + 1),
  }
}

function BudgetForm({ onSaved }: { onSaved: () => void }) {
  useTranslation()

  const { client } = useBudgetSession()
  const [form, setForm] = useState({
    global_cap_usd: '',
    easy: '',
    medium: '',
    hard: '',
    action: '' as 'pause' | 'downgrade' | '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const loaded = useRef(false)

  useEffect(() => {
    if (loaded.current) return
    loaded.current = true
    const controller = new AbortController()
    void client.getBudget(controller.signal).then(
      (budget) => {
        setForm({
          global_cap_usd:
            budget.global_cap_usd === undefined ||
            budget.global_cap_usd === null
              ? ''
              : String(budget.global_cap_usd),
          easy: budget.difficulty_caps?.easy
            ? String(budget.difficulty_caps.easy)
            : '',
          medium: budget.difficulty_caps?.medium
            ? String(budget.difficulty_caps.medium)
            : '',
          hard: budget.difficulty_caps?.hard
            ? String(budget.difficulty_caps.hard)
            : '',
          action: budget.action ?? '',
        })
      },
      () => {
        // 读取失败不阻塞编辑（保存仍可用）
      },
    )
    return () => controller.abort()
  }, [client])

  async function save() {
    if (busy) return
    const nextErrors = validateBudgetInput(form)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) return
    setBusy(true)
    setMessage(null)
    try {
      await client.saveBudget({
        global_cap_usd: form.global_cap_usd.trim()
          ? Number(form.global_cap_usd)
          : null,
        difficulty_caps: {
          easy: form.easy.trim() ? Number(form.easy) : null,
          medium: form.medium.trim() ? Number(form.medium) : null,
          hard: form.hard.trim() ? Number(form.hard) : null,
        },
        action: form.action === '' ? null : form.action,
      })
      setMessage('预算已保存。')
      onSaved()
    } catch (cause: unknown) {
      setMessage(cause instanceof Error ? cause.message : '保存失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-3">
      {message && <Alert message={t(message)} type="info" showIcon />}
      <label>
        {t(
          '全局预算上限（USD；留空提交表示保持现有上限——后端部分更新不清除，如需清空请联系管理员重置）',
        )}
        <Input
          aria-label={t('全局预算上限')}
          value={form.global_cap_usd}
          placeholder={t('如 100')}
          onChange={(event) =>
            setForm({ ...form, global_cap_usd: event.target.value })
          }
        />
        {errors.global_cap_usd && (
          <small role="alert">{t(errors.global_cap_usd)}</small>
        )}
      </label>
      <div className="evaluation-section-heading">
        {(['easy', 'medium', 'hard'] as const).map((key) => (
          <label key={key}>
            {{ easy: t('简单'), medium: t('中等'), hard: t('困难') }[key]}
            {t('上限')}
            <Input
              aria-label={t('{{value1}} 难度预算上限', { value1: key })}
              value={form[key]}
              placeholder={t('留空 = 保持现有值')}
              onChange={(event) =>
                setForm({ ...form, [key]: event.target.value })
              }
            />
            {errors[key] && <small role="alert">{t(errors[key])}</small>}
          </label>
        ))}
      </div>
      <label>
        {t('超限动作')}
        <Select
          aria-label={t('超限动作')}
          value={form.action || undefined}
          placeholder={t('不动作')}
          allowClear
          options={[
            { value: 'pause', label: t('暂停（pause）') },
            { value: 'downgrade', label: t('降级模型（downgrade）') },
          ]}
          onChange={(value) =>
            setForm({ ...form, action: (value ?? '') as typeof form.action })
          }
        />
      </label>
      <Button
        type="primary"
        aria-label={t('保存预算')}
        disabled={busy}
        onClick={() => void save()}
      >
        {busy ? t('保存中…') : t('保存预算')}
      </Button>
    </div>
  )
}

function UsageSection({ usage }: { usage: BudgetUsage }) {
  useTranslation()

  type Row = {
    cap_usd: number | null
    used_usd: number
    remaining_usd?: number | null
    percentage_used: number | null
  }
  const rows: Array<[string, Row]> = [
    [t('全局'), usage.global_budget],
    [t('简单'), usage.by_difficulty.easy],
    [t('中等'), usage.by_difficulty.medium],
    [t('困难'), usage.by_difficulty.hard],
  ]
  return (
    <table className="evaluation-list-table" aria-label={t('预算使用量')}>
      <thead>
        <tr>
          {[t('口径'), t('上限'), t('已用'), t('剩余'), t('使用率')].map(
            (name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ),
          )}
        </tr>
      </thead>
      <tbody>
        {rows.map(([name, section]) => (
          <tr key={name}>
            <td>{name}</td>
            <td>{formatUsd(section.cap_usd)}</td>
            <td>{formatUsd(section.used_usd)}</td>
            <td>{formatUsd(section.remaining_usd ?? null)}</td>
            <td>
              {section.percentage_used === null
                ? '—'
                : `${section.percentage_used}%`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function AlertRulesSection({ onChanged }: { onChanged: () => void }) {
  useTranslation()

  const { client } = useBudgetSession()
  const [rules, setRules] = useState<AlertRule[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState({
    name: '',
    threshold_pct: '80',
    channel: 'log' as AlertChannel,
    target: '',
  })
  const [draftError, setDraftError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(() => {
    const controller = new AbortController()
    void client.alertRules(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) {
          setRules(data)
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

  async function create() {
    if (busy) return
    const input = {
      name: draft.name.trim(),
      threshold_pct: Number(draft.threshold_pct),
      channel: draft.channel,
      target: draft.target.trim(),
    }
    const invalid = validateAlertInput(input)
    setDraftError(invalid)
    if (invalid) return
    setBusy(true)
    try {
      await client.createAlertRule({ ...input, enabled: true })
      setDraft({ name: '', threshold_pct: '80', channel: 'log', target: '' })
      reload()
      onChanged()
    } catch (cause: unknown) {
      setDraftError(cause instanceof Error ? cause.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  async function toggle(rule: AlertRule) {
    if (busy) return
    setBusy(true)
    try {
      await client.updateAlertRule(rule.id, { enabled: !rule.enabled })
      reload()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '操作失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  async function remove(rule: AlertRule) {
    if (busy) return
    if (
      !window.confirm(
        t('确认删除预警规则「{{value1}}」？', { value1: rule.name || rule.id }),
      )
    )
      return
    setBusy(true)
    try {
      await client.deleteAlertRule(rule.id)
      reload()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '删除失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-3">
      <Alert
        type="warning"
        showIcon
        message={t(
          '通知投递后端尚未实现：规则会被保存，但不会实际发送 Slack/Webhook/邮件通知。',
        )}
      />
      {error && <ExperimentFeedback message={t(error)} retry={reload} />}
      {rules === null && !error ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : rules && rules.length ? (
        <table className="evaluation-list-table" aria-label={t('预警规则')}>
          <thead>
            <tr>
              {[
                t('名称'),
                t('阈值'),
                t('渠道'),
                t('目标'),
                t('状态'),
                t('操作'),
              ].map((name) => (
                <th key={name} scope="col">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td>{rule.name || rule.id}</td>
                <td>{rule.threshold_pct}%</td>
                <td>{rule.channel}</td>
                <td>{rule.target || '—'}</td>
                <td>{rule.enabled ? t('启用') : t('停用')}</td>
                <td className="evaluation-section-heading">
                  <Button
                    size="small"
                    disabled={busy}
                    onClick={() => void toggle(rule)}
                  >
                    {rule.enabled ? t('停用') : t('启用')}
                  </Button>
                  <Button
                    size="small"
                    danger
                    disabled={busy}
                    onClick={() => void remove(rule)}
                  >
                    {t('删除')}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p role="status">{t('还没有预警规则。')}</p>
      )}
      <fieldset>
        <legend>{t('新增预警规则')}</legend>
        {draftError && <small role="alert">{draftError}</small>}
        <div className="evaluation-section-heading">
          <Input
            aria-label={t('规则名称')}
            placeholder={t('名称（可选）')}
            value={draft.name}
            onChange={(event) =>
              setDraft({ ...draft, name: event.target.value })
            }
          />
          <Input
            aria-label={t('阈值百分比')}
            placeholder={t('阈值 %（1–100）')}
            value={draft.threshold_pct}
            onChange={(event) =>
              setDraft({ ...draft, threshold_pct: event.target.value })
            }
          />
          <Select
            aria-label={t('通知渠道')}
            value={draft.channel}
            options={CHANNEL_OPTIONS.map((option) => ({ ...option }))}
            onChange={(value: AlertChannel) =>
              setDraft({ ...draft, channel: value })
            }
          />
          <Input
            aria-label={t('通知目标')}
            placeholder={
              draft.channel === 'log'
                ? t('log 渠道无需目标')
                : t('Webhook/邮箱等目标')
            }
            value={draft.target}
            onChange={(event) =>
              setDraft({ ...draft, target: event.target.value })
            }
          />
          <Button
            aria-label={t('创建预警规则')}
            disabled={busy}
            onClick={() => void create()}
          >
            {t('创建')}
          </Button>
        </div>
      </fieldset>
    </div>
  )
}

export default function BudgetsPage() {
  useTranslation()

  const { client } = useBudgetSession()
  const usage = useResource(
    useCallback((signal: AbortSignal) => client.usage(signal), [client]),
  )
  const refreshUsage = usage.retry
  return (
    <section className="mx-auto w-full max-w-3xl">
      <h1 className="mb-2 text-xl font-semibold">{t('预算与预警')}</h1>
      <p className="mb-6 text-neutral-600 dark:text-neutral-400">
        {t(
          '管理个人预算上限与成本预警规则；难度使用量为估算（按题目难度均摊）。',
        )}
      </p>
      <div className="grid gap-8">
        <div>
          <h2 className="mb-3 text-lg font-semibold">{t('预算配置')}</h2>
          <BudgetForm onSaved={refreshUsage} />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">{t('使用量')}</h2>
          {usage.loading ? (
            <Skeleton active paragraph={{ rows: 4 }} />
          ) : usage.error ? (
            <ExperimentFeedback message={t(usage.error)} retry={usage.retry} />
          ) : usage.data ? (
            <UsageSection usage={usage.data} />
          ) : null}
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">{t('预警规则')}</h2>
          <AlertRulesSection onChanged={refreshUsage} />
        </div>
      </div>
      <p className="mt-6">
        <Link to="/settings">{t('返回设置')}</Link>
      </p>
    </section>
  )
}
