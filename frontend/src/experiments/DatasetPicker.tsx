import type { AxiosInstance } from 'axios'
import { Alert, Button, Input, Select, Spin } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { t } from '../i18n/core.ts'
import { useAuthStore } from '../store/auth.ts'
import { readDatasets, type DatasetReference } from './datasets.ts'
import './DatasetPicker.css'

export default function DatasetPicker({
  datasetId,
  datasetPath,
  onChange,
  disabled = false,
  error,
}: {
  datasetId?: string
  datasetPath: string
  onChange: (source: { dataset_id: string; dataset_path: string }) => void
  disabled?: boolean
  error?: string
}) {
  useTranslation()
  const owner = useAuthStore((state) => state.session?.marker ?? null)
  const [mode, setMode] = useState(
    datasetId || !datasetPath ? 'personal' : 'path',
  )
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{
    owner: string | null
    attempt: number
    data?: DatasetReference[]
    error?: string
  }>()
  useEffect(() => {
    const controller = new AbortController()
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    void http
      .get('/datasets', { signal: controller.signal, timeout: 10_000 })
      .then(
        (value: unknown) => {
          if (!controller.signal.aborted) {
            try {
              setState({ owner, attempt, data: readDatasets(value) })
            } catch (error: unknown) {
              setState({
                owner,
                attempt,
                error:
                  error instanceof Error ? error.message : '数据集加载失败',
              })
            }
          }
        },
        () => {
          if (!controller.signal.aborted)
            setState({ owner, attempt, error: '数据集加载失败' })
        },
      )
    return () => controller.abort()
  }, [owner, attempt])
  const current =
    state?.owner === owner && state?.attempt === attempt ? state : undefined
  return (
    <div className="dataset-picker">
      <label>
        {t('数据来源')}
        <Select
          aria-label={t('数据来源')}
          value={mode}
          disabled={disabled}
          options={[
            { value: 'personal', label: t('个人题库') },
            { value: 'path', label: t('服务器数据集路径') },
          ]}
          onChange={(value: string) => {
            setMode(value)
            onChange({ dataset_id: '', dataset_path: '' })
          }}
        />
      </label>
      {mode === 'personal' ? (
        <>
          {!current ? (
            <Spin aria-label={t('加载个人题库')} />
          ) : current.error ? (
            <Alert
              type="error"
              showIcon
              message={t(current.error)}
              action={
                <Button
                  disabled={disabled}
                  onClick={() => setAttempt((value) => value + 1)}
                >
                  {t('重试')}
                </Button>
              }
            />
          ) : current.data?.some((item) => item.problem_count > 0) ? (
            <label>
              {t('选择个人题库')}
              <Select
                aria-label={t('选择个人题库')}
                placeholder={t('选择个人题库')}
                value={datasetId || undefined}
                disabled={disabled}
                options={current.data.map((item) => ({
                  value: item.id,
                  label: `${t('个人题库')} · ${item.problem_count} ${t('题')}`,
                  disabled: item.problem_count === 0,
                }))}
                onChange={(value: string) =>
                  onChange({ dataset_id: value, dataset_path: '' })
                }
              />
            </label>
          ) : (
            <p>
              {t('尚无可用个人题目，请先导入题库。')}{' '}
              <Link to="/problems">{t('前往题库')}</Link>
            </p>
          )}
          <p>{t('创建时保存题目快照，后续导入不会改变本次执行数据。')}</p>
        </>
      ) : (
        <label>
          {t('数据集路径（DATA_ROOT 下的相对路径）')}
          <Input
            aria-label={t('数据集路径')}
            value={datasetPath}
            placeholder="datasets/demo.json"
            disabled={disabled}
            onChange={(event) =>
              onChange({ dataset_id: '', dataset_path: event.target.value })
            }
          />
        </label>
      )}
      {error && <small role="alert">{t(error)}</small>}
    </div>
  )
}
