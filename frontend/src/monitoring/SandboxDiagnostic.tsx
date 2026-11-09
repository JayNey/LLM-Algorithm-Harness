import { Button } from 'antd'
import type { AxiosInstance } from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import { useAuthStore } from '../store/auth.ts'
import { createMonitoringClient } from './client.ts'
import { probeStatusLabel } from './presentation.ts'
import type { HealthCheck } from './types.ts'

type Diagnostic =
  | { phase: 'idle' | 'checking' | 'failed' }
  | { phase: 'checked'; result: HealthCheck }

export function SandboxDiagnostic() {
  useTranslation()

  const [diagnostic, setDiagnostic] = useState<Diagnostic>({ phase: 'idle' })
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])

  async function check() {
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setDiagnostic({ phase: 'checking' })
    try {
      const client = createMonitoringClient(
        useAuthStore.getState().httpClient() as AxiosInstance,
      )
      const result = await client.sandboxHealth(controller.signal)
      if (!controller.signal.aborted)
        setDiagnostic({ phase: 'checked', result })
    } catch {
      if (!controller.signal.aborted) setDiagnostic({ phase: 'failed' })
    } finally {
      request.current = null
    }
  }

  const { phase } = diagnostic
  const detail = phase === 'checked' ? diagnostic.result.detail : undefined
  const status =
    phase === 'checked'
      ? probeStatusLabel(diagnostic.result.status)
      : phase === 'checking'
        ? t('正在检查…')
        : t('未检查')

  return (
    <div role="group" aria-label={t('沙箱')} className="my-3 grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <strong>{t('沙箱')}</strong>
        {phase === 'failed' ? (
          <span role="alert">
            <span>{t('沙箱检查请求失败')}</span>
          </span>
        ) : (
          <span role="status">{status}</span>
        )}
        <Button
          size="small"
          loading={phase === 'checking'}
          disabled={phase === 'checking'}
          onClick={() => void check()}
        >
          {phase === 'failed' ? t('重试沙箱检查') : t('检查沙箱')}
        </Button>
      </div>
      {detail && <span className="break-words">{t(detail)}</span>}
    </div>
  )
}
