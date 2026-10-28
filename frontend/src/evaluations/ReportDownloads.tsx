import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, Button } from 'antd'
import type { AxiosInstance } from 'axios'
import { useAuthStore } from '../store/auth.ts'
import { t } from '../i18n/core.ts'
import { ApiClientError } from '../auth/http.ts'
import { createReportClient, type ReportFormat } from './reports.ts'

export function ReportDownloads({
  runId,
  complete,
}: {
  runId: string
  complete: boolean
}) {
  useTranslation()
  const client = useMemo(
    () =>
      createReportClient(useAuthStore.getState().httpClient() as AxiosInstance),
    [],
  )
  const [pending, setPending] = useState<ReportFormat | null>(null)
  const [error, setError] = useState<string | null>(null)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  async function download(format: ReportFormat) {
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setPending(format)
    setError(null)
    try {
      const file = await client.download(runId, format, controller.signal)
      if (controller.signal.aborted) return
      if (!(file.blob instanceof Blob)) throw new Error(t('报告响应格式不兼容'))
      const url = URL.createObjectURL(file.blob)
      const link = document.createElement('a')
      try {
        link.href = url
        link.download = file.filename
        document.body.append(link)
        link.click()
      } finally {
        link.remove()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        setError(
          cause instanceof ApiClientError &&
            (cause.status === 403 || cause.status === 404)
            ? t('报告不可访问，请确认当前账号和运行记录。')
            : cause instanceof Error
              ? cause.message
              : t('报告下载失败，请重试'),
        )
    } finally {
      if (!controller.signal.aborted) {
        request.current = null
        setPending(null)
      }
    }
  }
  return (
    <section aria-label={t('下载报告')}>
      {!complete && <p>{t('报告仅包含当前已记录的结果，不代表完整评估。')}</p>}
      <div className="evaluation-actions">
        {(['markdown', 'html', 'csv'] as const).map((format) => (
          <Button
            key={format}
            disabled={pending !== null}
            loading={pending === format}
            onClick={() => void download(format)}
          >
            {t('下载报告')} ·{' '}
            {format === 'markdown' ? 'Markdown' : format.toUpperCase()}
          </Button>
        ))}
      </div>
      {error && (
        <Alert
          role="alert"
          type="error"
          message={t('报告下载失败，请重试') + '：' + t(error)}
        />
      )}
    </section>
  )
}
