import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Input,
  InputNumber,
  Select,
  Space,
  Tabs,
} from 'antd'
import { useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ApiClientError } from '@/auth/http.ts'
import { EvaluationFeedback } from '@/evaluations/components.tsx'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import { useResource } from '@/hooks/useResource.ts'
import { currentLanguage, t } from '@/i18n/core.ts'
import { difficultyLabel } from '@/problems/presentation.ts'
import { useProblemSession } from '@/problems/session.tsx'
import type {
  ApiPage,
  ApprovedChange,
  GovernanceChange,
  GovernanceRequest,
} from '@/problems/types.ts'
import { useAuthStore } from '@/store/auth.ts'

const pageSize = 50

function useGovernanceChoices<T>(
  load: (offset: number, signal: AbortSignal) => Promise<ApiPage<T>>,
  toOption: (row: T) => { value: string; label: string },
) {
  const [offset, setOffset] = useState(0)
  const [options, setOptions] = useState<{ value: string; label: string }[]>([])
  const page = useResource(
    useCallback(
      async (signal: AbortSignal) => {
        const data = await load(offset, signal)
        if (!signal.aborted) {
          const optionsOnPage = data.items.map(toOption)
          setOptions((current) => {
            const indexed = new Map(
              current.map((option) => [option.value, option]),
            )
            for (const option of optionsOnPage)
              indexed.set(option.value, option)
            return [...indexed.values()]
          })
        }
        return data
      },
      [load, offset, toOption],
    ),
  )
  return {
    options,
    loading: page.loading,
    error: page.error,
    retry: page.retry,
    loadMore: page.data?.has_more
      ? () => setOffset(offset + pageSize)
      : undefined,
  }
}

function problemOption(row: { problem_id: string; title: string }) {
  return { value: row.problem_id, label: `${row.title} · ${row.problem_id}` }
}

function historyOption(row: {
  id: string
  model: string | null
  created_at: string
}) {
  const date = new Date(row.created_at)
  return {
    value: row.id,
    label: [
      row.model,
      Number.isNaN(date.getTime())
        ? null
        : date.toLocaleString(currentLanguage()),
      row.id,
    ]
      .filter(Boolean)
      .join(' · '),
  }
}

function hasTagNormalization(change: GovernanceChange) {
  return (
    JSON.stringify(change.original_tags) !==
    JSON.stringify(change.standard_tags)
  )
}

function hasDifficultyChange(change: GovernanceChange) {
  return (
    change.sample_count > 0 &&
    change.original_difficulty !== change.suggested_difficulty
  )
}

function percent(value: number | null) {
  return value === null
    ? '—'
    : new Intl.NumberFormat(currentLanguage(), {
        style: 'percent',
        maximumFractionDigits: 2,
      }).format(value)
}

function tagList(tags: string[]) {
  return tags.length ? tags.join(', ') : '—'
}

function ReviewProblem({
  change,
  approved,
  onChange,
}: {
  change: GovernanceChange
  approved?: ApprovedChange
  onChange: (patch: Partial<Omit<ApprovedChange, 'problem_id'>>) => void
}) {
  const selected = approved?.suggested_tags ?? []
  return (
    <fieldset className="panel evaluation-panel min-w-0">
      <legend>
        {change.title || change.problem_id} · {change.problem_id}
      </legend>
      <p>
        {t('原标签')} · {tagList(change.original_tags)}
      </p>
      <p>
        {t('标准标签')} · {tagList(change.standard_tags)}
      </p>
      {hasTagNormalization(change) && (
        <Checkbox
          checked={approved?.normalize_tags ?? false}
          onChange={(event) =>
            onChange({ normalize_tags: event.target.checked })
          }
        >
          {t('应用标准标签')}
        </Checkbox>
      )}
      {change.suggestions.length > 0 && (
        <div>
          <h4>{t('建议标签')}</h4>
          <ul className="evaluation-problem-list">
            {change.suggestions.map((suggestion) => (
              <li key={suggestion.tag}>
                <Checkbox
                  checked={selected.includes(suggestion.tag)}
                  onChange={(event) =>
                    onChange({
                      suggested_tags: event.target.checked
                        ? [...selected, suggestion.tag]
                        : selected.filter((tag) => tag !== suggestion.tag),
                    })
                  }
                >
                  <span>{suggestion.tag}</span>
                  <small>
                    {t('匹配关键词')} · {tagList(suggestion.matched_keywords)} ·{' '}
                    {t('置信度')} {percent(suggestion.confidence)}
                  </small>
                </Checkbox>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p>
        {t('原难度')} · {difficultyLabel(change.original_difficulty)} →{' '}
        {t('建议难度')} · {difficultyLabel(change.suggested_difficulty)}
      </p>
      <p>
        {t('有效样本数')} · {change.sample_count} · {t('通过率')} ·{' '}
        {percent(change.pass_rate)}
      </p>
      {!change.sample_count && <p>{t('没有有效的历史执行，保留原难度。')}</p>}
      {hasDifficultyChange(change) && (
        <Checkbox
          checked={approved?.apply_difficulty ?? false}
          onChange={(event) =>
            onChange({ apply_difficulty: event.target.checked })
          }
        >
          {t('应用建议难度')}
        </Checkbox>
      )}
    </fieldset>
  )
}

function GovernanceReview({ onSaved }: { onSaved: (id: string) => void }) {
  const { client, owner } = useProblemSession()
  const { client: evaluations } = useEvaluationSession()
  const problems = useGovernanceChoices(
    useCallback(
      (offset: number, signal: AbortSignal) =>
        client.problems(
          { source: 'personal', offset, limit: pageSize },
          signal,
        ),
      [client],
    ),
    problemOption,
  )
  const history = useGovernanceChoices(
    useCallback(
      (offset: number, signal: AbortSignal) =>
        evaluations.results({ offset, limit: pageSize }, signal),
      [evaluations],
    ),
    historyOption,
  )
  const [ids, setIds] = useState<string[]>([])
  const [runs, setRuns] = useState<string[]>([])
  const [easy, setEasy] = useState<number | null>(70)
  const [hard, setHard] = useState<number | null>(30)
  const [request, setRequest] = useState<GovernanceRequest | null>(null)
  const [approved, setApproved] = useState(
    () => new Map<string, ApprovedChange>(),
  )
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const saveLock = useRef(false)
  const preview = useResource(
    useCallback(
      (signal: AbortSignal) =>
        request
          ? client.previewGovernance(request, signal)
          : Promise.resolve(null),
      [client, request],
    ),
  )
  const choices = [...approved.values()].filter(
    (item) =>
      item.normalize_tags ||
      item.apply_difficulty ||
      item.suggested_tags.length,
  )
  const invalidThresholds =
    easy === null || hard === null || hard >= easy || hard < 0 || easy > 100

  function clearPreview() {
    setRequest(null)
    setApproved(new Map())
    setError(null)
  }

  function review() {
    if (!ids.length || invalidThresholds) return
    clearPreview()
    setRequest({
      problem_ids: ids,
      run_ids: runs,
      easy_threshold: easy / 100,
      hard_threshold: hard / 100,
    })
  }

  async function save() {
    if (
      saveLock.current ||
      !request ||
      !preview.data ||
      !choices.length ||
      !name.trim()
    )
      return
    saveLock.current = true
    setSaving(true)
    setError(null)
    try {
      const version = await client.saveDatasetVersion({
        name: name.trim(),
        preview: request,
        preview_token: preview.data.preview_token,
        changes: choices,
      })
      if (useAuthStore.getState().session?.marker !== owner) return
      clearPreview()
      setName('')
      onSaved(version.id)
    } catch (failure) {
      if (useAuthStore.getState().session?.marker !== owner) return
      if (failure instanceof ApiClientError && failure.status === 409) {
        clearPreview()
        setError('题库或历史已更新，请重新预览。')
      } else {
        setError('保存题集版本失败，请重试。')
      }
    } finally {
      saveLock.current = false
      setSaving(false)
    }
  }

  const canApply = preview.data?.problems.some(
    (change) =>
      hasTagNormalization(change) ||
      hasDifficultyChange(change) ||
      change.suggestions.length > 0,
  )
  return (
    <div className="evaluation-workflow">
      <div className="form-grid">
        <div>
          <label htmlFor="governance-problems">{t('选择个人题目')}</label>
          <Select
            id="governance-problems"
            mode="multiple"
            maxCount={500}
            style={{ width: '100%' }}
            value={ids}
            options={problems.options}
            loading={problems.loading}
            disabled={saving}
            showSearch={{ optionFilterProp: 'label' }}
            onChange={(value: string[]) => {
              setIds(value)
              clearPreview()
            }}
          />
          {!problems.loading && !problems.error && !problems.options.length && (
            <p>{t('个人题库还没有题目。')}</p>
          )}
          {problems.error && (
            <EvaluationFeedback
              message={t(problems.error)}
              retry={problems.retry}
            />
          )}
          {problems.loadMore && (
            <Button onClick={problems.loadMore}>{t('加载更多题目')}</Button>
          )}
        </div>
        <div>
          <label htmlFor="governance-history">
            {t('选择历史评估（可选）')}
          </label>
          <Select
            id="governance-history"
            mode="multiple"
            maxCount={100}
            style={{ width: '100%' }}
            value={runs}
            options={history.options}
            loading={history.loading}
            disabled={saving}
            showSearch={{ optionFilterProp: 'label' }}
            onChange={(value: string[]) => {
              setRuns(value)
              clearPreview()
            }}
          />
          {history.error && (
            <EvaluationFeedback
              message={t(history.error)}
              retry={history.retry}
            />
          )}
          {history.loadMore && (
            <Button onClick={history.loadMore}>{t('加载更多评估')}</Button>
          )}
        </div>
      </div>
      <div className="form-grid">
        <div>
          <label htmlFor="governance-hard">{t('困难阈值（%）')}</label>
          <InputNumber
            id="governance-hard"
            value={hard}
            min={0}
            max={100}
            disabled={saving}
            onChange={(value) => {
              setHard(value)
              clearPreview()
            }}
          />
        </div>
        <div>
          <label htmlFor="governance-easy">{t('简单阈值（%）')}</label>
          <InputNumber
            id="governance-easy"
            value={easy}
            min={0}
            max={100}
            disabled={saving}
            onChange={(value) => {
              setEasy(value)
              clearPreview()
            }}
          />
        </div>
      </div>
      {invalidThresholds ? (
        <p role="alert">
          {t('困难阈值必须低于简单阈值，且两者都在 0–100% 之间。')}
        </p>
      ) : (
        <p>{t('通过率低于困难阈值为困难，高于简单阈值为简单，其余为中等。')}</p>
      )}
      <div className="evaluation-actions">
        <Button
          type="primary"
          disabled={!ids.length || invalidThresholds || saving}
          loading={!!request && preview.loading}
          onClick={review}
        >
          {t('预览变更')}
        </Button>
      </div>
      {preview.error && (
        <EvaluationFeedback message={t(preview.error)} retry={preview.retry} />
      )}
      {error && <Alert type="error" title={t(error)} showIcon />}
      {preview.data && (
        <>
          {preview.data.problems.map((change) => (
            <ReviewProblem
              key={change.problem_id}
              change={change}
              approved={approved.get(change.problem_id)}
              onChange={(patch) => {
                if (saveLock.current) return
                setApproved((current) =>
                  new Map(current).set(change.problem_id, {
                    problem_id: change.problem_id,
                    normalize_tags: false,
                    suggested_tags: [],
                    apply_difficulty: false,
                    ...current.get(change.problem_id),
                    ...patch,
                  }),
                )
              }}
            />
          ))}
          {!canApply ? (
            <Alert type="info" title={t('所选题目没有可应用的变更。')} />
          ) : (
            <div className="evaluation-actions">
              <Input
                aria-label={t('题集版本名称')}
                placeholder={t('题集版本名称')}
                maxLength={120}
                value={name}
                disabled={saving}
                onChange={(event) => setName(event.target.value)}
              />
              <Button
                type="primary"
                loading={saving}
                disabled={!choices.length || !name.trim()}
                onClick={() => void save()}
              >
                {t('保存题集版本')}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function SavedVersions({
  versionId,
  onSelect,
}: {
  versionId: string | null
  onSelect: (id: string) => void
}) {
  const { client } = useProblemSession()
  const versions = useResource(
    useCallback(
      (signal: AbortSignal) => client.datasetVersions(signal),
      [client],
    ),
  )
  const selected = useResource(
    useCallback(
      (signal: AbortSignal) =>
        versionId
          ? client.datasetVersion(versionId, signal)
          : Promise.resolve(null),
      [client, versionId],
    ),
  )
  return (
    <div className="evaluation-workflow">
      <label htmlFor="dataset-versions">{t('选择已保存的题集版本')}</label>
      <Select
        id="dataset-versions"
        loading={versions.loading}
        value={versionId ?? undefined}
        style={{ width: '100%' }}
        onChange={onSelect}
        options={versions.data?.map((version) => ({
          value: version.id,
          label: `${version.name} · ${t('{{count}} 道题目', { count: version.problem_count })}`,
        }))}
      />
      {versions.data?.length === 0 && (
        <p role="status">{t('还没有保存的题集版本。')}</p>
      )}
      {versions.error && (
        <EvaluationFeedback
          message={t(versions.error)}
          retry={versions.retry}
        />
      )}
      {versionId && selected.loading && (
        <p role="status">{t('正在加载题集版本…')}</p>
      )}
      {selected.error && (
        <EvaluationFeedback
          message={t(selected.error)}
          retry={selected.retry}
        />
      )}
      {selected.data && (
        <section className="panel evaluation-panel">
          <Space wrap className="evaluation-section-heading">
            <h3>{selected.data.name}</h3>
            <Link
              className="evaluation-create-link"
              to={`/evaluations/new?dataset_version=${encodeURIComponent(selected.data.id)}`}
            >
              {t('使用此版本创建评估')}
            </Link>
          </Space>
          <ul className="evaluation-problem-list">
            {selected.data.problems.map((problem) => (
              <li key={problem.problem_id}>
                <span>{problem.title}</span>
                <small>
                  {problem.problem_id} · {difficultyLabel(problem.difficulty)} ·{' '}
                  {tagList(problem.tags)}
                </small>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

export function GovernancePanel({ onClose }: { onClose: () => void }) {
  useTranslation()
  const [tab, setTab] = useState('review')
  const [versionId, setVersionId] = useState<string | null>(null)
  const [savedCount, setSavedCount] = useState(0)
  return (
    <Drawer open title={t('批量治理')} size="large" onClose={onClose}>
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: 'review',
            label: t('预览与审核'),
            children: (
              <GovernanceReview
                onSaved={(id) => {
                  setVersionId(id)
                  setSavedCount((count) => count + 1)
                  setTab('versions')
                }}
              />
            ),
          },
          {
            key: 'versions',
            label: t('题集版本'),
            children: (
              <SavedVersions
                key={savedCount}
                versionId={versionId}
                onSelect={setVersionId}
              />
            ),
          },
        ]}
      />
    </Drawer>
  )
}
