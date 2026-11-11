import {
  Alert,
  Button,
  Checkbox,
  Input,
  InputNumber,
  Select,
  Space,
} from 'antd'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiClientError } from '@/auth/http.ts'
import { t } from '@/i18n/core.ts'
import { difficultyLabel } from '@/problems/presentation.ts'
import type {
  LeetCodeBatchItem,
  LeetCodeCandidate,
  LeetCodeDifficulty,
  ProblemClient,
} from '@/problems/types.ts'

export type BatchOutcome = LeetCodeBatchItem & { jobId: string }

const failures: Record<string, string> = {
  unavailable: 'LeetCode 题目不存在或无法公开访问。',
  timeout: 'LeetCode 请求超时，请重试。',
  rate_limit: 'LeetCode 请求触发限流，请稍后重试。',
  upstream: '暂时无法连接 LeetCode，请稍后重试。',
  library_limit: '个人题库已达到容量上限。',
}

export function LeetCodeBatchImport({
  client,
  blocked,
  submitting,
  submitError,
  outcomes,
  onSubmit,
}: {
  client: ProblemClient
  blocked: boolean
  submitting: boolean
  submitError: string | null
  outcomes: BatchOutcome[]
  onSubmit: (slugs: string[], retryJobId?: string) => void
}) {
  useTranslation()
  const id = useId()
  const [tagInput, setTagInput] = useState('')
  const [difficulty, setDifficulty] = useState<LeetCodeDifficulty | null>(null)
  const [limit, setLimit] = useState<number | null>(20)
  const [previewing, setPreviewing] = useState(false)
  const [candidates, setCandidates] = useState<LeetCodeCandidate[] | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const tags = tagInput
    .split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
  const validLimit =
    limit !== null && Number.isInteger(limit) && limit >= 1 && limit <= 50
  const failed = outcomes.filter((item) => item.status === 'failed')

  function clearPreview() {
    setCandidates(null)
    setSelected([])
    setError(null)
  }

  async function preview() {
    if (previewing || !validLimit || (!tags.length && difficulty === null))
      return
    if (
      tags.length > 10 ||
      tags.some(
        (tag) =>
          tag.length > 150 ||
          !/^[a-z0-9]+(?:-[a-z0-9]+)*$/i.test(tag.replace(/\s+/g, '-')),
      )
    ) {
      setError('请输入最多 10 个英文标签，用逗号分隔。')
      return
    }
    clearPreview()
    setPreviewing(true)
    try {
      setCandidates(await client.previewLeetCode({ tags, difficulty, limit }))
    } catch (cause) {
      const status = cause instanceof ApiClientError ? cause.status : null
      setError(
        status === 429
          ? failures.rate_limit
          : status === 408
            ? failures.timeout
            : '无法预览 LeetCode 题目，请稍后重试。',
      )
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <section aria-labelledby={`${id}-heading`}>
      <h4 id={`${id}-heading`}>{t('按标签和难度批量导入')}</h4>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void preview()
        }}
      >
        <Space wrap align="end">
          <div>
            <label htmlFor={`${id}-tags`}>{t('标签（逗号分隔）')}</label>
            <Input
              id={`${id}-tags`}
              placeholder="Dynamic Programming"
              value={tagInput}
              disabled={previewing}
              maxLength={1510}
              onChange={(event) => {
                setTagInput(event.target.value)
                clearPreview()
              }}
            />
          </div>
          <div>
            <label htmlFor={`${id}-difficulty`}>{t('难度')}</label>
            <br />
            <Select<LeetCodeDifficulty>
              id={`${id}-difficulty`}
              aria-label={t('难度')}
              allowClear
              placeholder={t('不限难度')}
              style={{ minWidth: 128 }}
              disabled={previewing}
              value={difficulty ?? undefined}
              options={(['easy', 'medium', 'hard'] as const).map((value) => ({
                value,
                label: difficultyLabel(value),
              }))}
              onChange={(value) => {
                setDifficulty(value ?? null)
                clearPreview()
              }}
            />
          </div>
          <div>
            <label htmlFor={`${id}-limit`}>{t('最多导入（1–50）')}</label>
            <br />
            <InputNumber
              id={`${id}-limit`}
              min={1}
              max={50}
              precision={0}
              value={limit}
              disabled={previewing}
              onChange={(value) => {
                setLimit(value)
                clearPreview()
              }}
            />
          </div>
          <Button
            htmlType="submit"
            loading={previewing}
            disabled={!validLimit || (!tags.length && difficulty === null)}
          >
            {t('预览公开题目')}
          </Button>
        </Space>
      </form>

      {error && <Alert role="alert" type="error" title={t(error)} />}
      {submitError && (
        <Alert role="alert" type="error" title={t(submitError)} />
      )}
      {candidates?.length === 0 && (
        <p role="status">{t('没有符合条件的公开题目。')}</p>
      )}
      {!!candidates?.length && (
        <div aria-label={t('LeetCode 候选题目')}>
          <Checkbox
            checked={selected.length === candidates.length}
            indeterminate={
              selected.length > 0 && selected.length < candidates.length
            }
            onChange={(event) =>
              setSelected(
                event.target.checked ? candidates.map(({ slug }) => slug) : [],
              )
            }
          >
            {t('全选候选题')}
          </Checkbox>
          <ul style={{ maxHeight: 320, overflowY: 'auto' }}>
            {candidates.map((candidate) => (
              <li key={candidate.slug}>
                <Space wrap>
                  <Checkbox
                    checked={selected.includes(candidate.slug)}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, candidate.slug]
                          : current.filter((slug) => slug !== candidate.slug),
                      )
                    }
                  >
                    {candidate.number}. {candidate.title}
                  </Checkbox>
                  <span>{difficultyLabel(candidate.difficulty)}</span>
                  {candidate.tags.length > 0 && (
                    <span>{candidate.tags.join(' · ')}</span>
                  )}
                  <a
                    href={candidate.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {t('在 LeetCode 查看原题')}
                  </a>
                </Space>
              </li>
            ))}
          </ul>
          <Button
            type="primary"
            loading={submitting}
            disabled={blocked || selected.length === 0}
            onClick={() => onSubmit(selected)}
          >
            {t('确认导入 {{count}} 道题', { count: selected.length })}
          </Button>
        </div>
      )}

      {outcomes.length > 0 && (
        <div aria-label={t('LeetCode 批量导入结果')}>
          <p role="status">
            {t(
              '成功 {{imported}} · 跳过重复 {{duplicates}} · 失败 {{failed}}',
              {
                imported: outcomes.filter((item) => item.status === 'imported')
                  .length,
                duplicates: outcomes.filter(
                  (item) => item.status === 'duplicate',
                ).length,
                failed: failed.length,
              },
            )}
          </p>
          {failed.length > 0 && (
            <ul>
              {failed.map((item) => (
                <li key={item.slug}>
                  <Space wrap>
                    <a
                      href={`https://leetcode.com/problems/${item.slug}/`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {candidates?.find(
                        (candidate) => candidate.slug === item.slug,
                      )?.title ?? item.slug}
                    </a>
                    <span>
                      {t(failures[item.error ?? ''] ?? '导入失败，请重试')}
                    </span>
                    {item.retryable && (
                      <Button
                        size="small"
                        disabled={blocked}
                        onClick={() => onSubmit([item.slug], item.jobId)}
                      >
                        {t('重试这道题')}
                      </Button>
                    )}
                  </Space>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
