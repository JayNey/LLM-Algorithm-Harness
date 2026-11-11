import {
  Alert,
  Button,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Tabs,
} from 'antd'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { ApiClientError } from '../auth/http.ts'
import { useResource } from '../hooks/useResource.ts'
import { currentLanguage, t } from '../i18n/core.ts'
import { EvaluationFeedback } from './components.tsx'
import { useEvaluationSession } from './session.tsx'
import type { ProblemQuery, ResultSummary } from './types.ts'

type UseSelection = (ids: string[]) => void

const emptyMessages = {
  insufficient_history:
    '所选历史中的有效样本不足。请选择更多评估或降低最少样本数。',
  no_weaknesses: '所选历史中没有达到失败率阈值的题型。',
  no_candidates: '所选题库中没有匹配的未评估题目。',
}

function percent(value: number) {
  return new Intl.NumberFormat(currentLanguage(), {
    style: 'percent',
    maximumFractionDigits: 1,
  }).format(value)
}

function groupLabel(key: string) {
  const [type, ...parts] = key.split(':')
  const value = parts.join(':')
  switch (type) {
    case 'difficulty':
      return `${t('难度')} · ${t(value)}`
    case 'tag':
      return `${t('标签')} · ${value}`
    case 'tags':
      return `${t('标签组合')} · ${value}`
    case 'difficulty_tags': {
      const [difficulty, tags] = value.split('|', 2)
      return `${t('难度与标签')} · ${t(difficulty)} / ${tags}`
    }
    default:
      return key
  }
}

export function RecommendationPanel({
  evaluationId,
  onClose,
}: {
  evaluationId?: string
  onClose: () => void
}) {
  useTranslation()
  const { owner } = useEvaluationSession()
  const navigate = useNavigate()
  const [savedVersion, setSavedVersion] = useState(0)
  const continueWith: UseSelection = (ids) => {
    if (owner && ids.length)
      void navigate('/evaluations/new', {
        state: { recommendedFor: owner, recommendedProblemIds: ids },
      })
  }

  return (
    <Modal
      open
      width={760}
      title={evaluationId ? t('推荐下一轮题目') : t('个人推荐题集')}
      footer={null}
      onCancel={onClose}
    >
      {evaluationId ? (
        <Tabs
          items={[
            {
              key: 'preview',
              label: t('推荐预览'),
              children: (
                <RecommendationPreview
                  evaluationId={evaluationId}
                  continueWith={continueWith}
                  onSaved={() => setSavedVersion((version) => version + 1)}
                />
              ),
            },
            {
              key: 'saved',
              label: t('个人推荐题集'),
              children: (
                <SavedRecommendationSets
                  key={savedVersion}
                  continueWith={continueWith}
                />
              ),
            },
          ]}
        />
      ) : (
        <SavedRecommendationSets continueWith={continueWith} />
      )}
    </Modal>
  )
}

function RecommendationPreview({
  evaluationId,
  continueWith,
  onSaved,
}: {
  evaluationId: string
  continueWith: UseSelection
  onSaved: () => void
}) {
  const { client } = useEvaluationSession()
  const [runIds, setRunIds] = useState([evaluationId])
  const [source, setSource] = useState<ProblemQuery['source']>('all')
  const [minSamples, setMinSamples] = useState<number | null>(1)
  const [request, setRequest] = useState<
    Parameters<typeof client.previewRecommendations>[0] | null
  >({ run_ids: [evaluationId], source: 'all', min_samples: 1 })
  const [selected, setSelected] = useState<string[]>([])
  const [name, setName] = useState('')
  const [save, setSave] = useState<{
    pending?: boolean
    success?: boolean
    error?: string
  }>({})
  const [offset, setOffset] = useState(0)
  const [knownHistory, setKnownHistory] = useState<ResultSummary[]>([])

  const history = useResource(
    useCallback(
      async (signal: AbortSignal) => {
        const page = await client.results({ limit: 20, offset }, signal)
        if (!signal.aborted) {
          setKnownHistory((known) => [
            ...known.filter(
              (item) => !page.items.some((next) => next.id === item.id),
            ),
            ...page.items,
          ])
        }
        return page
      },
      [client, offset],
    ),
  )
  const preview = useResource(
    useCallback(
      (signal: AbortSignal) =>
        request
          ? client.previewRecommendations(request, signal)
          : Promise.resolve(null),
      [client, request],
    ),
  )
  const selectedIds =
    preview.data?.problems
      .filter((item) => selected.includes(item.problem_id))
      .map((item) => item.problem_id) ?? []

  function clearPreview() {
    setRequest(null)
    setSelected([])
    setSave({})
  }

  async function saveSelection() {
    if (save.pending || !name.trim() || !selectedIds.length) return
    setSave({ pending: true })
    try {
      await client.saveRecommendationSet(name.trim(), selectedIds)
      setSave({ success: true })
      setName('')
      onSaved()
    } catch (error) {
      setSave({
        error:
          error instanceof ApiClientError
            ? error.message
            : t('保存题集失败，请重试。'),
      })
    }
  }

  return (
    <>
      <Form
        layout="vertical"
        disabled={save.pending}
        onFinish={() => {
          if (!runIds.length || !minSamples) return
          setSelected([])
          setSave({})
          setRequest({ run_ids: runIds, source, min_samples: minSamples })
        }}
      >
        <Form.Item label={t('历史评估')} htmlFor="recommendation-history">
          <Select
            id="recommendation-history"
            mode="multiple"
            maxCount={20}
            value={runIds}
            optionFilterProp="label"
            loading={history.loading}
            options={[
              { value: evaluationId, label: t('当前运行') },
              ...knownHistory
                .filter((item) => item.id !== evaluationId)
                .map((item) => ({
                  value: item.id,
                  label: [
                    item.model,
                    new Date(item.created_at).toLocaleString(currentLanguage()),
                    item.run_id ?? item.id,
                  ]
                    .filter(Boolean)
                    .join(' · '),
                })),
            ]}
            onChange={(ids) => {
              setRunIds(ids)
              clearPreview()
            }}
          />
          {history.error && (
            <EvaluationFeedback
              message={t(history.error)}
              retry={history.retry}
            />
          )}
          {history.data?.has_more && (
            <Button type="link" onClick={() => setOffset(offset + 20)}>
              {t('加载更多历史评估')}
            </Button>
          )}
        </Form.Item>
        <div className="form-grid">
          <Form.Item label={t('候选题库')} htmlFor="recommendation-source">
            <Select
              id="recommendation-source"
              value={source}
              options={[
                { value: 'all', label: t('全部来源') },
                { value: 'shared', label: t('共享题库') },
                { value: 'personal', label: t('本人导入') },
              ]}
              onChange={(value) => {
                setSource(value)
                clearPreview()
              }}
            />
          </Form.Item>
          <Form.Item
            label={t('最少样本数')}
            htmlFor="recommendation-min-samples"
          >
            <InputNumber
              id="recommendation-min-samples"
              min={1}
              max={1000}
              precision={0}
              value={minSamples}
              onChange={(value) => {
                setMinSamples(value)
                clearPreview()
              }}
            />
          </Form.Item>
        </div>
        <Button
          htmlType="submit"
          loading={request !== null && preview.loading}
          disabled={!runIds.length || !minSamples}
        >
          {t('预览推荐')}
        </Button>
      </Form>

      {preview.error && (
        <EvaluationFeedback message={t(preview.error)} retry={preview.retry} />
      )}
      {!!preview.data?.weaknesses.length && (
        <>
          <h3>{t('薄弱题型')}</h3>
          <ul>
            {preview.data.weaknesses.map((item) => (
              <li key={item.key}>
                {t('{{group}} · 失败率 {{rate}} · {{count}} 个样本', {
                  group: groupLabel(item.key),
                  rate: percent(item.failure_rate),
                  count: item.total,
                })}
              </li>
            ))}
          </ul>
        </>
      )}
      {preview.data?.empty_reason && (
        <Alert
          type="info"
          showIcon
          title={t(emptyMessages[preview.data.empty_reason])}
        />
      )}
      {!!preview.data?.problems.length && (
        <>
          <h3>{t('推荐题目')}</h3>
          <ul className="evaluation-problem-list">
            {preview.data.problems.map((item) => (
              <li key={item.problem_id}>
                <Checkbox
                  disabled={save.pending}
                  checked={selected.includes(item.problem_id)}
                  onChange={(event) =>
                    setSelected((ids) =>
                      event.target.checked
                        ? [...ids, item.problem_id]
                        : ids.filter((id) => id !== item.problem_id),
                    )
                  }
                >
                  <span>{item.title || item.problem_id}</span>
                  <small>
                    {item.problem_id} · {t(item.difficulty ?? '难度未知')}
                  </small>
                  <small>
                    {t(
                      '匹配 {{groups}}。最高失败率 {{rate}}（{{count}} 个样本）',
                      {
                        groups: item.matching_groups
                          .map(groupLabel)
                          .join(' / '),
                        rate: percent(item.failure_rate),
                        count: item.total,
                      },
                    )}
                  </small>
                </Checkbox>
              </li>
            ))}
          </ul>
          <div className="evaluation-actions">
            <Input
              aria-label={t('题集名称')}
              placeholder={t('题集名称')}
              value={name}
              maxLength={100}
              disabled={save.pending}
              onChange={(event) => setName(event.target.value)}
            />
            <Button
              loading={save.pending}
              disabled={!selectedIds.length || !name.trim()}
              onClick={() => void saveSelection()}
            >
              {t('保存个人题集')}
            </Button>
            <Button
              type="primary"
              disabled={!selectedIds.length || save.pending}
              onClick={() => continueWith(selectedIds)}
            >
              {t('带选题创建评估')}
            </Button>
          </div>
          {save.success && (
            <p role="status">{t('题集已保存，可在个人推荐题集中打开。')}</p>
          )}
          {save.error && <EvaluationFeedback message={t(save.error)} />}
        </>
      )}
    </>
  )
}

function SavedRecommendationSets({
  continueWith,
}: {
  continueWith: UseSelection
}) {
  const { client } = useEvaluationSession()
  const [setId, setSetId] = useState<string>()
  const sets = useResource(client.recommendationSets)
  const opened = useResource(
    useCallback(
      (signal: AbortSignal) =>
        setId ? client.recommendationSet(setId, signal) : Promise.resolve(null),
      [client, setId],
    ),
  )
  return (
    <>
      {sets.error && (
        <EvaluationFeedback message={t(sets.error)} retry={sets.retry} />
      )}
      {sets.data?.length === 0 && <p>{t('还没有保存的推荐题集。')}</p>}
      {!!sets.data?.length && (
        <Form layout="vertical">
          <Form.Item label={t('打开题集')} htmlFor="recommendation-set">
            <Select
              id="recommendation-set"
              value={setId}
              options={sets.data.map((item) => ({
                value: item.id,
                label: item.name,
              }))}
              onChange={setSetId}
            />
          </Form.Item>
        </Form>
      )}
      {setId && opened.loading && <p role="status">{t('正在读取题集…')}</p>}
      {opened.error && (
        <EvaluationFeedback message={t(opened.error)} retry={opened.retry} />
      )}
      {opened.data && (
        <>
          {!!opened.data.unavailable_count && (
            <Alert
              type="warning"
              showIcon
              title={t('{{count}} 道题已无法访问。', {
                count: opened.data.unavailable_count,
              })}
            />
          )}
          <ul>
            {opened.data.problems.map((item) => (
              <li key={item.problem_id}>
                {item.title || item.problem_id} ·{' '}
                {t(item.difficulty ?? '难度未知')}
              </li>
            ))}
          </ul>
          <Button
            type="primary"
            disabled={!opened.data.problems.length}
            onClick={() =>
              continueWith(
                opened.data?.problems.map((item) => item.problem_id) ?? [],
              )
            }
          >
            {t('用此题集创建评估')}
          </Button>
        </>
      )}
    </>
  )
}
