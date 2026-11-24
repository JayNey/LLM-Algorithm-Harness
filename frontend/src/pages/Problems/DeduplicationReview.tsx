import { Alert, Button, Input, InputNumber } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClientError } from '@/auth/http.ts'
import { EvaluationFeedback } from '@/evaluations/components.tsx'
import { useResource } from '@/hooks/useResource.ts'
import { t } from '@/i18n/core.ts'
import { useProblemSession } from '@/problems/session.tsx'
import type { DuplicateGroup, DuplicateProblem } from '@/problems/types.ts'
import { useAuthStore } from '@/store/auth.ts'

function content(value: unknown) {
  return JSON.stringify(value, null, 2) ?? '—'
}

function MergeReview({
  group,
  primary,
}: {
  group: DuplicateGroup
  primary: string
}) {
  const original = group.problems.find(
    (p) => p.problem_id === primary,
  ) as DuplicateProblem
  const merged = group.merges[primary]
  const fields = [
    ...new Set([...Object.keys(original), ...Object.keys(merged)]),
  ].filter((key) => content(original[key]) !== content(merged[key]))
  return (
    <>
      <h4>{t('合并前后的字段变化')}</h4>
      <div style={{ overflowX: 'auto' }}>
        <table aria-label={t('合并前后的字段变化')}>
          <thead>
            <tr>
              <th>{t('字段')}</th>
              <th>{t('合并前')}</th>
              <th>{t('合并后')}</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((field) => (
              <tr key={field}>
                <th scope="row">{field}</th>
                <td>
                  <pre>{content(original[field])}</pre>
                </td>
                <td>
                  <pre>{content(merged[field])}</pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>{t('合并后的题目')}</summary>
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
          {content(merged)}
        </pre>
      </details>
    </>
  )
}

export function DeduplicationReview({
  onSaved,
}: {
  onSaved: (id: string) => void
}) {
  const { client, owner } = useProblemSession()
  const [threshold, setThreshold] = useState<number | null>(0.9)
  const [request, setRequest] = useState<{ threshold: number } | null>(null)
  const [choices, setChoices] = useState<Record<string, string>>({})
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lock = useRef(false)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])
  const current = () =>
    alive.current && useAuthStore.getState().session?.marker === owner
  const preview = useResource(
    useCallback(
      (signal: AbortSignal) =>
        request
          ? client.previewDeduplication(request, signal)
          : Promise.resolve(null),
      [client, request],
    ),
  )
  const selected =
    preview.data?.groups.flatMap((group) =>
      choices[group.group_id]
        ? [{ group_id: group.group_id, primary_id: choices[group.group_id] }]
        : [],
    ) ?? []
  async function save() {
    if (
      lock.current ||
      !current() ||
      !preview.data ||
      !request ||
      !selected.length ||
      !name.trim()
    )
      return
    lock.current = true
    setSaving(true)
    setError(null)
    try {
      const version = await client.saveDeduplication({
        ...request,
        preview_token: preview.data.preview_token,
        name: name.trim(),
        groups: selected,
      })
      if (current()) onSaved(version.id)
    } catch (err) {
      if (!current()) return
      if (err instanceof ApiClientError && err.status === 409) {
        setRequest(null)
        setChoices({})
        setError('题库已更新，请重新扫描并确认。')
      } else if (err instanceof ApiClientError && err.status === 410) {
        setRequest(null)
        setChoices({})
        setError('已保存的版本已不可用，请重新扫描。')
      } else setError('保存题集版本失败，请重试。')
    } finally {
      lock.current = false
      if (current()) setSaving(false)
    }
  }
  return (
    <div className="evaluation-workflow">
      <p>{t('扫描不会修改个人题库。逐组选定保留题，合并只保存到新版本。')}</p>
      <label htmlFor="deduplication-threshold">{t('文本相似度阈值')}</label>
      <InputNumber
        id="deduplication-threshold"
        aria-label={t('文本相似度阈值')}
        min={0}
        max={1}
        step={0.01}
        value={threshold}
        disabled={saving}
        onChange={(value) => {
          setThreshold(value)
          setRequest(null)
          setChoices({})
          setError(null)
        }}
      />
      <Button
        disabled={
          saving ||
          threshold === null ||
          !Number.isFinite(threshold) ||
          threshold < 0 ||
          threshold > 1
        }
        loading={!!request && preview.loading}
        onClick={() => {
          if (threshold === null || lock.current) return
          setChoices({})
          setError(null)
          setRequest({ threshold })
        }}
      >
        {t('扫描相似题')}
      </Button>
      {preview.error && (
        <EvaluationFeedback message={t(preview.error)} retry={preview.retry} />
      )}
      {error && <Alert type="error" title={t(error)} showIcon />}
      {preview.data && (
        <>
          {preview.data.groups.length === 0 && (
            <p role="status">{t('没有发现相似题。')}</p>
          )}
          {preview.data.groups.map((group, index) => (
            <fieldset
              className="panel evaluation-panel min-w-0"
              key={group.group_id}
              disabled={saving}
            >
              <legend>{t('候选组 {{number}}', { number: index + 1 })}</legend>
              <ul>
                {group.problems.map((problem) => (
                  <li key={problem.problem_id}>
                    <strong>
                      {problem.title} · {problem.problem_id}
                    </strong>
                    <p>
                      {t('来源')} · {String(problem.source_platform ?? '—')} ·{' '}
                      {String(problem.source_problem_id ?? '—')}
                    </p>
                    <details>
                      <summary>{t('原题内容与元数据')}</summary>
                      <pre
                        style={{
                          whiteSpace: 'pre-wrap',
                          overflowWrap: 'anywhere',
                        }}
                      >
                        {content(problem)}
                      </pre>
                    </details>
                  </li>
                ))}
              </ul>
              <ul>
                {group.matches.map((match) => (
                  <li key={match.left_id + ':' + match.right_id}>
                    {match.left_id} ↔ {match.right_id} ·{' '}
                    {match.fingerprint && t('来源指纹相同')}
                    {match.similarity !== null && (
                      <>
                        {' '}
                        · {t('文本相似度')}{' '}
                        {(match.similarity * 100).toFixed(2)}%
                      </>
                    )}
                  </li>
                ))}
              </ul>
              <p>
                {t('推荐保留题')} · {group.recommended_primary_id}
              </p>
              <label>
                {t('保留题')}{' '}
                <select
                  value={choices[group.group_id] ?? ''}
                  onChange={(event) => {
                    if (lock.current) return
                    setChoices((previous) => ({
                      ...previous,
                      [group.group_id]: event.target.value,
                    }))
                  }}
                >
                  <option value="">{t('跳过整组')}</option>
                  {group.problems.map((problem) => (
                    <option key={problem.problem_id} value={problem.problem_id}>
                      {problem.title} · {problem.problem_id}
                    </option>
                  ))}
                </select>
              </label>
              {choices[group.group_id] && (
                <MergeReview group={group} primary={choices[group.group_id]} />
              )}
            </fieldset>
          ))}
          {!!preview.data.groups.length && (
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
                disabled={!selected.length || !name.trim()}
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
