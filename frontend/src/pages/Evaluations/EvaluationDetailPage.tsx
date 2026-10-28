import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button } from 'antd'
import { useCallback, useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useStore } from 'zustand'
import {
  EvaluationFeedback,
  EvaluationFacts,
} from '@/evaluations/components.tsx'
import { useAuthStore } from '@/store/auth.ts'
import { useEvaluationSession } from '@/evaluations/session.tsx'
import {
  isLiveStatus,
  useEvaluation,
  useEvaluationLive,
} from '@/evaluations/useEvaluation.ts'
import '@/evaluations/workflow.css'

export default function EvaluationDetailPage() {
  useTranslation()

  const { evaluationId = '' } = useParams()
  const { owner, client, creationStore } = useEvaluationSession()
  const receipt = useStore(creationStore)
  const detail = useEvaluation(client, evaluationId, owner)
  // 非终态评估挂载进度观察器（WS 订阅 + HTTP 快照对账，issue #225 Step 4）
  const liveEnabled = !!detail.data && isLiveStatus(detail.data.status)
  const live = useEvaluationLive(client, evaluationId, owner, liveEnabled)
  const current =
    live.forbidden || live.unauthorized
      ? undefined
      : (live.evaluation ?? detail.data)
  const readError = live.forbidden
    ? t('任务不可访问，请刷新后重试')
    : (live.error ?? detail.error)
  const authClear = useAuthStore((state) => state.clear)
  useEffect(() => {
    // WS/HTTP 双通道恢复失败 → 清会话，由 RequireSession 携返回路径回跳登录
    if (live.unauthorized) authClear()
  }, [live.unauthorized, authClear])
  const busy =
    ['creating', 'created', 'starting'].includes(receipt.phase) ||
    !!receipt.action?.pending
  const actionScope = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    actionScope.current = controller
    return () => {
      controller.abort()
      actionScope.current = null
    }
  }, [evaluationId, owner])
  const previous = useRef(busy)
  const { reload } = detail
  const { refresh: refreshLive, runMutation } = live
  const refresh = useCallback(() => {
    if (liveEnabled) refreshLive()
    else reload()
  }, [liveEnabled, refreshLive, reload])
  useEffect(() => {
    // Also refresh when the create page's automatic start finishes after navigation.
    if (
      previous.current &&
      !busy &&
      receipt.action?.evaluationId !== evaluationId
    )
      refresh()
    previous.current = busy
  }, [busy, refresh, receipt.action?.evaluationId, evaluationId])
  async function act(kind: 'start' | 'cancel') {
    const signal = actionScope.current?.signal
    if (!signal) return
    const operation = () => receipt.act(evaluationId, kind, signal)
    if (liveEnabled) await runMutation(operation)
    else {
      await operation()
      if (!signal.aborted) reload()
    }
  }
  const actionError =
    receipt.action?.evaluationId === evaluationId
      ? receipt.action.error
      : receipt.evaluationId === evaluationId
        ? receipt.error
        : null
  return (
    <section className="evaluation-workflow">
      <header className="page-heading">
        <div>
          <h1>{t('评估任务详情')}</h1>
          <p>{t('查看任务状态与费用，按当前支持的操作管理任务。')}</p>
        </div>
        <Link to="/evaluations">{t('返回任务列表')}</Link>
      </header>
      <section
        className="panel evaluation-panel"
        aria-label={t('评估详情')}
        aria-busy={detail.loading || busy}
      >
        <dl className="evaluation-receipt">
          <dt>{t('任务 ID')}</dt>
          <dd>{evaluationId}</dd>
        </dl>
        {actionError && (
          <Alert
            showIcon
            type="warning"
            title={
              receipt.phase === 'start-error'
                ? t('任务已创建，启动尚未确认')
                : t('操作尚未确认')
            }
            description={t('{{value1}}。请核对最新任务状态后重试。', {
              value1: actionError.message,
            })}
          />
        )}
        {detail.loading && <p role="status">{t('正在加载评估详情…')}</p>}
        {readError && (
          <EvaluationFeedback
            message={t(
              current
                ? t('{{value1}}；下方为上次读取的数据，请刷新后操作。', {
                    value1: readError,
                  })
                : readError,
            )}
            retry={refresh}
          />
        )}
        {current && <EvaluationFacts evaluation={current} />}
        {live.mode === 'live' && <p role="status">{t('实时进度已连接')}</p>}
        {live.mode === 'degraded' && (
          <p role="status">{t('实时通道不可用，已切换为轮询。')}</p>
        )}
        <div className="evaluation-actions">
          <Button onClick={refresh} disabled={detail.loading || busy}>
            {t('刷新任务')}
          </Button>
          {current?.can_start && (
            <Button
              type="primary"
              disabled={busy || detail.loading || !!readError}
              onClick={() => {
                void act('start')
              }}
            >
              {t('启动任务')}
            </Button>
          )}
          {current?.can_cancel && (
            <Button
              danger
              disabled={busy || detail.loading || !!readError}
              onClick={() => {
                void act('cancel')
              }}
            >
              {t('取消任务')}
            </Button>
          )}
          {busy && <span role="status">{t('正在等待操作响应…')}</span>}
        </div>
      </section>
    </section>
  )
}
