import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Input, Select, Skeleton } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExperimentFeedback } from '@/experiments/components.tsx'
import { useBudgetSession } from '@/budgets/session.tsx'
import type {
  AlertChannel,
  AlertRule,
  BudgetUsage,
  CostRange,
} from '@/budgets/types.ts'
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
  const [editing, setEditing] = useState<AlertRule | null>(null)
  const [editDraft, setEditDraft] = useState({
    name: '',
    threshold_pct: '80',
    channel: 'log' as AlertChannel,
    target: '',
    enabled: true,
  })

  async function saveEdit() {
    if (!editing || busy) return
    const input = {
      name: editDraft.name.trim(),
      threshold_pct: Number(editDraft.threshold_pct),
      channel: editDraft.channel,
      target: editDraft.target.trim(),
      enabled: editDraft.enabled,
    }
    const invalid = validateAlertInput(input)
    if (invalid) {
      setError(invalid)
      return
    }
    setBusy(true)
    try {
      await client.updateAlertRule(editing.id, input)
      setEditing(null)
      reload()
      onChanged()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '保存失败，请重试')
    } finally {
      setBusy(false)
    }
  }

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
          '预警由 Web 评估 worker 在启动、恢复和成本结算时检查，需要个人全局预算及启用的规则。保存规则不会立即发送，也不代表投递成功；其他任务类型不会独立触发检查。Slack/Webhook 使用规则中的 HTTPS 目标；邮件需要部署方配置 worker 的 COST_ALERT_SMTP_*。站内通知中心仍为 Mock。',
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
            {rules.map((rule) =>
              editing?.id === rule.id ? (
                <tr key={rule.id}>
                  <td>
                    <Input
                      aria-label={t('编辑规则名称')}
                      value={editDraft.name}
                      onChange={(event) =>
                        setEditDraft({ ...editDraft, name: event.target.value })
                      }
                    />
                  </td>
                  <td>
                    <Input
                      aria-label={t('编辑阈值百分比')}
                      value={editDraft.threshold_pct}
                      onChange={(event) =>
                        setEditDraft({
                          ...editDraft,
                          threshold_pct: event.target.value,
                        })
                      }
                    />
                  </td>
                  <td>
                    <Select
                      aria-label={t('编辑通知渠道')}
                      value={editDraft.channel}
                      options={CHANNEL_OPTIONS.map((option) => ({ ...option }))}
                      onChange={(value: AlertChannel) =>
                        setEditDraft({ ...editDraft, channel: value })
                      }
                    />
                  </td>
                  <td>
                    <Input
                      aria-label={t('编辑通知目标')}
                      value={editDraft.target}
                      onChange={(event) =>
                        setEditDraft({
                          ...editDraft,
                          target: event.target.value,
                        })
                      }
                    />
                  </td>
                  <td>{editDraft.enabled ? t('启用') : t('停用')}</td>
                  <td className="evaluation-section-heading">
                    <Button
                      size="small"
                      type="primary"
                      disabled={busy}
                      onClick={() => void saveEdit()}
                    >
                      {t('保存')}
                    </Button>
                    <Button
                      size="small"
                      disabled={busy}
                      onClick={() => setEditing(null)}
                    >
                      {t('取消')}
                    </Button>
                  </td>
                </tr>
              ) : (
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
                      onClick={() => {
                        setEditing(rule)
                        setEditDraft({
                          name: rule.name,
                          threshold_pct: String(rule.threshold_pct),
                          channel: rule.channel as AlertChannel,
                          target: rule.target,
                          enabled: rule.enabled,
                        })
                      }}
                    >
                      {t('编辑')}
                    </Button>
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
              ),
            )}
          </tbody>
        </table>
      ) : (
        <p role="status">{t('还没有预警规则。')}</p>
      )}
      <fieldset>
        <legend>{t('新增预警规则')}</legend>
        {draftError && <small role="alert">{t(draftError)}</small>}
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

function CostOverviewSection() {
  useTranslation()

  const { client } = useBudgetSession()
  const [rangeKey, setRangeKey] = useState<'7' | '30' | 'all'>('30')
  const load = useCallback(
    (signal: AbortSignal) => {
      const range: CostRange =
        rangeKey === 'all'
          ? { since: null, until: null }
          : {
              since: new Date(
                Date.now() - (rangeKey === '7' ? 7 : 30) * 86_400_000,
              )
                .toISOString()
                .slice(0, 10),
              until: null,
            }
      return Promise.all([
        client.costSummary(range, signal),
        client.costTrends(range, signal),
        client.costBreakdown(range, signal),
      ])
    },
    [client, rangeKey],
  )
  const state = useResource(load)
  const [summary, trends, breakdown] = state.data ?? []

  const unknownNote = (count: number, reasons: Record<string, number>) =>
    count > 0
      ? t(
          '统计含 {{value1}} 条未知费用记录（{{value2}}）；已知费用合计为下限，不是精确总额。',
          {
            value1: count,
            value2:
              Object.entries(reasons)
                .map(([key, value]) => `${key}×${value}`)
                .join(', ') || '—',
          },
        )
      : null

  return (
    <div className="grid gap-3">
      <label className="flex items-center gap-2">
        {t('时间范围')}
        <Select
          aria-label={t('费用时间范围')}
          value={rangeKey}
          onChange={(value: '7' | '30' | 'all') => setRangeKey(value)}
          options={[
            { value: '7', label: t('近 7 天') },
            { value: '30', label: t('近 30 天') },
            { value: 'all', label: t('全部') },
          ]}
          style={{ width: 160 }}
        />
      </label>
      {state.loading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : state.error ? (
        <ExperimentFeedback message={t(state.error)} retry={state.retry} />
      ) : summary && trends && breakdown ? (
        <>
          {!summary.cost_complete && (
            <Alert
              type="warning"
              showIcon
              message={t('部分调用缺少定价或用量，费用统计不完整。')}
              description={unknownNote(
                summary.unknown_cost_count,
                summary.unknown_reasons,
              )}
            />
          )}
          <table className="evaluation-list-table" aria-label={t('费用汇总')}>
            <tbody>
              <tr>
                <th scope="row">{t('已知费用合计')}</th>
                <td>{formatUsd(summary.known_cost_usd ?? null)}</td>
              </tr>
              <tr>
                <th scope="row">{t('任务数')}</th>
                <td>{summary.task_count}</td>
              </tr>
            </tbody>
          </table>
          <h3 className="mt-2 font-medium">{t('每日费用趋势')}</h3>
          <table
            className="evaluation-list-table"
            aria-label={t('每日费用趋势')}
          >
            <thead>
              <tr>
                {[t('日期'), t('已知费用（USD）'), t('未知费用条数')].map(
                  (name) => (
                    <th key={name} scope="col">
                      {name}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {trends.data.length ? (
                [...trends.data].reverse().map((point) => (
                  <tr key={point.date}>
                    <td>{point.date}</td>
                    <td>{formatUsd(point.known_cost_usd)}</td>
                    <td>{point.unknown_cost_count}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3}>{t('所选范围内暂无费用记录')}</td>
                </tr>
              )}
            </tbody>
          </table>
          <h3 className="mt-2 font-medium">{t('费用分项')}</h3>
          {(
            [
              [t('按来源'), breakdown.by_source],
              [t('按模型'), breakdown.by_model],
              [t('按策略'), breakdown.by_strategy],
            ] as const
          ).map(([label, rows]) => (
            <table
              key={label}
              className="evaluation-list-table"
              aria-label={label}
            >
              <caption className="text-left">{label}</caption>
              <thead>
                <tr>
                  {[t('条目'), t('已知费用（USD）')].map((name) => (
                    <th key={name} scope="col">
                      {name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.entries(rows).length ? (
                  Object.entries(rows).map(([key, value]) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>{formatUsd(value)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={2}>{t('暂无数据')}</td>
                  </tr>
                )}
              </tbody>
            </table>
          ))}
          {unknownNote(
            breakdown.unknown_cost_count,
            breakdown.unknown_reasons,
          ) && (
            <p className="text-neutral-600 dark:text-neutral-400">
              {unknownNote(
                breakdown.unknown_cost_count,
                breakdown.unknown_reasons,
              )}
            </p>
          )}
        </>
      ) : null}
    </div>
  )
}

function AlertHistorySection() {
  useTranslation()

  const { client } = useBudgetSession()
  const load = useCallback(
    (signal: AbortSignal) =>
      Promise.all([client.alertHistory(signal), client.alertRules(signal)]),
    [client],
  )
  const state = useResource(load)
  const [history, rules] = state.data ?? [null, null]
  const ruleName = (ruleId: string) =>
    rules?.find((rule) => rule.id === ruleId)?.name || ruleId.slice(0, 8)

  return (
    <div className="grid gap-3">
      {state.loading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : state.error ? (
        <ExperimentFeedback message={t(state.error)} retry={state.retry} />
      ) : history && history.length ? (
        <table className="evaluation-list-table" aria-label={t('预警投递历史')}>
          <thead>
            <tr>
              {[
                t('触发时间'),
                t('规则'),
                t('阈值'),
                t('已用 / 上限（USD）'),
                t('渠道'),
              ].map((name) => (
                <th key={name} scope="col">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history.map((event) => (
              <tr key={event.id}>
                <td>{event.triggered_at}</td>
                <td>{ruleName(event.rule_id)}</td>
                <td>{event.threshold_pct}%</td>
                <td>
                  {formatUsd(event.used_usd)} / {formatUsd(event.cap_usd)}
                </td>
                <td>{event.channel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-neutral-600 dark:text-neutral-400">
          {t('暂无预警投递历史；已配置规则只会在真实预算检查越过阈值时记录。')}
        </p>
      )}
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
        <div>
          <h2 className="mb-3 text-lg font-semibold">{t('费用概览')}</h2>
          <CostOverviewSection />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">{t('预警投递历史')}</h2>
          <AlertHistorySection />
        </div>
      </div>
      <p className="mt-6">
        <Link to="/settings">{t('返回设置')}</Link>
      </p>
    </section>
  )
}
