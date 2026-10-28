import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, Checkbox, Form, Input, Select, Skeleton } from 'antd'
import type { AxiosInstance } from 'axios'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useStore } from 'zustand'
import { readApiKeys } from '@/account/apiKeys.ts'
import { ApiClientError } from '@/auth/http.ts'
import { EvaluationFeedback } from '@/evaluations/components.tsx'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import type { DraftErrors, ProblemQuery } from '@/evaluations/types.ts'
import { validateDraft } from '@/evaluations/validation.ts'
import { useAuthStore } from '@/store/auth.ts'
import '@/evaluations/workflow.css'

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
            error:
              error instanceof ApiClientError
                ? error.message
                : '加载失败，请重试',
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

export default function CreateEvaluationPage() {
  useTranslation()

  const { client, creationStore, owner } = useEvaluationSession()
  const { draft, phase, evaluationId, error, setDraft, submit, reset } =
    useStore(creationStore)
  const [errors, setErrors] = useState<DraftErrors>({})
  const [query, setQuery] = useState<ProblemQuery>({
    source: 'all',
    offset: 0,
    limit: 20,
  })
  const [verified, setVerified] = useState<{
    source: ProblemQuery['source']
    ids: string[]
  }>({ source: 'all', ids: [] })
  const options = useResource(
    useCallback((signal: AbortSignal) => client.options(signal), [client]),
  )
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
  const models = useResource(
    useCallback(
      async (signal: AbortSignal) => {
        if (!draft.api_key_id) return null
        return client.models(draft.api_key_id, signal)
      },
      [client, draft.api_key_id],
    ),
  )
  const problems = useResource(
    useCallback(
      async (signal: AbortSignal) => {
        const data = await client.problems(query, signal)
        if (!signal.aborted)
          setVerified((previous) => ({
            source: query.source,
            ids: [
              ...new Set([
                ...(previous.source === query.source ? previous.ids : []),
                ...data.items.map((item) => item.problem_id),
              ]),
            ],
          }))
        return data
      },
      [client, query],
    ),
  )
  const editing = phase === 'editing'
  const ready = !!(
    keys.data?.length &&
    options.data?.strategies.length &&
    options.data.sources.length &&
    models.data?.models.length &&
    problems.data?.total
  )
  const locked = !editing || !ready || problems.loading || models.loading
  function create() {
    if (locked) return
    const next = validateDraft(draft, {
      api_key_ids: keys.data?.map((key) => key.id) ?? [],
      models: models.data?.models ?? [],
      strategy_names:
        options.data?.strategies.map((strategy) => strategy.name) ?? [],
      problem_ids: verified.source === query.source ? verified.ids : [],
    })
    setErrors(next)
    if (!Object.keys(next).length) void submit()
  }
  function selectProblem(id: string, checked: boolean) {
    setDraft({
      problem_ids: checked
        ? [...new Set([...draft.problem_ids, id])]
        : draft.problem_ids.filter((selected) => selected !== id),
    })
  }
  const currentIds = problems.data?.items.map((item) => item.problem_id) ?? []
  const selectedCount = currentIds.filter((id) =>
    draft.problem_ids.includes(id),
  ).length
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('创建评估')}</h1>
          <p>{t('选择模型、题目与策略，创建后立即请求启动。')}</p>
        </div>
        <Link to="/evaluations">{t('返回任务列表')}</Link>
      </header>
      {phase === 'create-unknown' ? (
        <div className="panel evaluation-panel">
          <Alert
            type="warning"
            showIcon
            title={t('创建结果尚未确认')}
            description={t(
              '请求未返回明确结果，任务可能已经创建。请先查看任务列表并核对，避免重复创建。',
            )}
          />
          <div className="evaluation-actions">
            <Link to="/evaluations">{t('查看任务列表')}</Link>
            <Button
              onClick={() => {
                reset(owner)
                setErrors({})
              }}
            >
              {t('确认核对后开始新评估')}
            </Button>
          </div>
        </div>
      ) : evaluationId ? (
        <div className="panel evaluation-panel">
          <p>{t('任务已创建。')}</p>
          <Link to={`/evaluations/${encodeURIComponent(evaluationId)}`}>
            {t('查看任务 ')}
            {evaluationId}
          </Link>
        </div>
      ) : (
        <Form
          layout="vertical"
          noValidate
          onFinish={create}
          disabled={!editing}
        >
          <div className="panel evaluation-panel">
            <h2>{t('模型与策略')}</h2>
            <div className="form-grid">
              <Form.Item
                label={t('API 密钥')}
                htmlFor="evaluation-key"
                required
                validateStatus={errors.api_key_id ? 'error' : undefined}
                help={t(errors.api_key_id)}
              >
                <Select
                  id="evaluation-key"
                  aria-label={t('API 密钥')}
                  placeholder={t('选择已保存的密钥')}
                  value={draft.api_key_id || undefined}
                  loading={keys.loading}
                  options={keys.data?.map((key) => ({
                    value: key.id,
                    label: `${key.key_name} · ${key.provider}`,
                  }))}
                  onChange={(value: string) => {
                    setDraft({ api_key_id: value })
                    setErrors({})
                  }}
                />
                {keys.error ? (
                  <EvaluationFeedback
                    message={t(keys.error)}
                    retry={keys.retry}
                  />
                ) : null}
                {keys.data?.length === 0 ? (
                  <p>
                    {t('还没有可用密钥，请先')}
                    <Link to="/settings/api-keys">{t('添加 API 密钥')}</Link>。
                  </p>
                ) : (
                  <Link to="/settings/api-keys">{t('管理 API 密钥')}</Link>
                )}
              </Form.Item>
              <Form.Item
                label={t('模型')}
                htmlFor="evaluation-model"
                required
                validateStatus={errors.model ? 'error' : undefined}
                help={t(errors.model)}
              >
                <Select
                  id="evaluation-model"
                  aria-label={t('模型')}
                  placeholder={
                    draft.api_key_id ? t('选择模型') : t('请先选择密钥')
                  }
                  showSearch
                  optionFilterProp="label"
                  value={draft.model || undefined}
                  disabled={
                    !editing ||
                    !draft.api_key_id ||
                    models.loading ||
                    !models.data?.models.length
                  }
                  loading={models.loading && !!draft.api_key_id}
                  options={models.data?.models.map((model) => ({
                    value: model,
                    label: model,
                  }))}
                  onChange={(value: string) => setDraft({ model: value })}
                />
                {models.error ? (
                  <EvaluationFeedback
                    message={t(models.error)}
                    retry={models.retry}
                  />
                ) : null}
                {models.data && !models.data.complete ? (
                  <p role="status">
                    {t('模型列表未完整加载，仅可选择已返回的模型。')}
                  </p>
                ) : null}
                {models.data?.models.length === 0 ? (
                  <p>
                    {t('该密钥未返回可用模型，请更换密钥或')}
                    <Button type="link" onClick={models.retry}>
                      {t('重新加载')}
                    </Button>
                    。
                  </p>
                ) : null}
              </Form.Item>
              <Form.Item
                label={t('策略')}
                htmlFor="evaluation-strategies"
                required
                validateStatus={errors.strategy_names ? 'error' : undefined}
                help={t(errors.strategy_names)}
              >
                <Select
                  id="evaluation-strategies"
                  aria-label={t('策略')}
                  mode="multiple"
                  placeholder={t('选择评估策略')}
                  value={draft.strategy_names}
                  loading={options.loading}
                  options={options.data?.strategies.map(({ name }) => ({
                    value: name,
                    label: name,
                  }))}
                  onChange={(value: string[]) =>
                    setDraft({ strategy_names: value })
                  }
                />
              </Form.Item>
              <Form.Item
                label={t('预算上限（USD，可选）')}
                htmlFor="evaluation-budget"
                validateStatus={errors.budget_cap_usd ? 'error' : undefined}
                help={t(
                  errors.budget_cap_usd ??
                    t('留空不设置上限；0 表示预算为 0 美元。'),
                )}
              >
                <Input
                  id="evaluation-budget"
                  inputMode="decimal"
                  value={draft.budget_cap_usd}
                  onChange={(event) => {
                    setDraft({ budget_cap_usd: event.target.value })
                    setErrors((current) => ({
                      ...current,
                      budget_cap_usd: undefined,
                    }))
                  }}
                />
              </Form.Item>
            </div>
            {options.error ? (
              <EvaluationFeedback
                message={t(options.error)}
                retry={options.retry}
              />
            ) : null}
            {options.data?.strategies.length === 0 ? (
              <p>{t('当前没有可用策略，暂时无法创建评估。')}</p>
            ) : null}
          </div>
          <div className="panel evaluation-panel">
            <div className="evaluation-section-heading">
              <h2>{t('评估题目')}</h2>
              <span aria-live="polite">
                {t('已选 ')}
                {draft.problem_ids.length} {t(' 道题目')}
              </span>
            </div>
            <Form.Item label={t('题目来源')} htmlFor="evaluation-source">
              <Select
                id="evaluation-source"
                aria-label={t('题目来源')}
                value={query.source}
                options={[
                  { value: 'all', label: t('全部来源') },
                  ...(options.data?.sources.map((source) => ({
                    value: source.id,
                    label: `${source.label}（${source.problem_count}）`,
                  })) ?? []),
                ]}
                onChange={(source: ProblemQuery['source']) => {
                  setDraft({ problem_ids: [] })
                  setQuery({ ...query, source, offset: 0 })
                  setErrors({})
                }}
              />
              <p>{t('切换来源会清空已选题目。全选仅选择当前页。')}</p>
            </Form.Item>
            {options.data?.sources.length === 0 ? (
              <p>{t('当前没有可用题目来源。')}</p>
            ) : null}
            {errors.problem_ids ? (
              <p role="alert" className="evaluation-field-error">
                {t(errors.problem_ids)}
              </p>
            ) : null}
            {problems.loading ? (
              <Skeleton active={false} paragraph={{ rows: 4 }} title={false} />
            ) : problems.error ? (
              <EvaluationFeedback
                message={t(problems.error)}
                retry={problems.retry}
              />
            ) : problems.data?.items.length ? (
              <>
                <Checkbox
                  disabled={!editing}
                  checked={selectedCount === currentIds.length}
                  indeterminate={
                    selectedCount > 0 && selectedCount < currentIds.length
                  }
                  onChange={(event) =>
                    setDraft({
                      problem_ids: event.target.checked
                        ? [...new Set([...draft.problem_ids, ...currentIds])]
                        : draft.problem_ids.filter(
                            (id) => !currentIds.includes(id),
                          ),
                    })
                  }
                >
                  {t('全选当前页')}
                </Checkbox>
                <ul className="evaluation-problem-list">
                  {problems.data.items.map((problem) => (
                    <li key={problem.problem_id}>
                      <Checkbox
                        aria-label={t('选择题目 {{value1}}', {
                          value1: problem.problem_id,
                        })}
                        disabled={!editing}
                        checked={draft.problem_ids.includes(problem.problem_id)}
                        onChange={(event) =>
                          selectProblem(
                            problem.problem_id,
                            event.target.checked,
                          )
                        }
                      >
                        <span>{problem.title || problem.problem_id}</span>
                        <small>
                          {problem.problem_id} ·{' '}
                          {problem.source === 'personal'
                            ? t('个人')
                            : t('共享')}{' '}
                          · {problem.difficulty ?? t('难度未知')}
                        </small>
                      </Checkbox>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p>{t('该来源还没有可用题目，请更换来源。')}</p>
            )}
            <div className="evaluation-pagination">
              <span>
                {t('共 ')}
                {problems.data?.total ?? '—'} {t(' 道题目')}
              </span>
              <Button
                aria-label={t('上一页题目')}
                disabled={!editing || problems.loading || query.offset === 0}
                onClick={() =>
                  setQuery({
                    ...query,
                    offset: Math.max(0, query.offset - query.limit),
                  })
                }
              >
                {t('上一页')}
              </Button>
              <Button
                aria-label={t('下一页题目')}
                disabled={
                  !editing || problems.loading || !problems.data?.has_more
                }
                onClick={() =>
                  setQuery({ ...query, offset: query.offset + query.limit })
                }
              >
                {t('下一页')}
              </Button>
            </div>
          </div>
          {error ? <EvaluationFeedback message={t(error.message)} /> : null}
          <div className="evaluation-actions">
            <Button
              type="primary"
              htmlType="submit"
              loading={phase === 'creating'}
              disabled={locked}
            >
              {t('创建并启动')}
            </Button>
            {!ready ? (
              <span>{t('请先加载可用密钥、模型、策略与题目。')}</span>
            ) : null}
          </div>
        </Form>
      )}
    </section>
  )
}
