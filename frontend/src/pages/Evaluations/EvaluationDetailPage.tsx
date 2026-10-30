import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { Alert, Button, InputNumber, Modal } from 'antd'
import { ApiClientError } from '@/auth/http.ts'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
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
  const { evaluationId = '' } = useParams()
  return <EvaluationDetail key={evaluationId} />
}

function EvaluationDetail() {
  useTranslation()

  const { evaluationId = '' } = useParams()
  const { owner, client, creationStore } = useEvaluationSession()
  const navigate = useNavigate()
  const [managementPending, setManagementPending] = useState(false)
  const managementLock = useRef(false)
  const [managementError, setManagementError] = useState<string | null>(null)
  const [managementSuccess, setManagementSuccess] = useState(false)
  const [budget, setBudget] = useState<number | null | undefined>(undefined)
  const [confirmDelete, setConfirmDelete] = useState(false)
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
    managementPending ||
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
    reload()
    if (liveEnabled) refreshLive()
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
    if (!signal || managementLock.current || busy) return
    const operation = () => receipt.act(evaluationId, kind, signal)
    if (liveEnabled) await runMutation(operation)
    else {
      await operation()
      if (!signal.aborted) reload()
    }
  }
  async function manage(kind: 'pause' | 'resume' | 'update' | 'delete') {
    const signal = actionScope.current?.signal
    if (
      !signal ||
      signal.aborted ||
      busy ||
      managementLock.current ||
      detail.loading ||
      readError ||
      !current
    )
      return
    if (!current[`can_${kind}`]) return
    const taskId = current.async_task_id
    if ((kind === 'pause' || kind === 'resume') && !taskId) return
    if (
      kind === 'update' &&
      (budget == null || !Number.isFinite(budget) || budget < 0)
    )
      return
    managementLock.current = true
    setManagementPending(true)
    setManagementError(null)
    setManagementSuccess(false)
    try {
      await runMutation(async () => {
        if (signal.aborted) return
        if (kind === 'pause' || kind === 'resume')
          await client[kind](taskId!, signal)
        else if (kind === 'update')
          await client.update(evaluationId, { budget_cap_usd: budget! }, signal)
        else await client.delete(evaluationId, signal)
      })
      if (signal.aborted) return
      if (kind === 'delete') {
        void navigate('/evaluations', { replace: true })
        return
      }
      setBudget(undefined)
      setManagementSuccess(true)
    } catch (error) {
      if (signal.aborted) return
      const status = error instanceof ApiClientError ? error.status : undefined
      setManagementError(
        status === 401
          ? '登录会话已失效'
          : status === 403 || status === 404
            ? '任务不可访问，请刷新后重试'
            : status === 400 || status === 409
              ? '任务状态已变化，请核对最新状态。'
              : '操作结果未确认，请核对最新状态后再操作。',
      )
    } finally {
      if (!signal.aborted) {
        managementLock.current = false
        setManagementPending(false)
        setConfirmDelete(false)
        refresh()
      }
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
              value1: t(actionError.message),
            })}
          />
        )}
        {managementError && (
          <Alert
            showIcon
            type="warning"
            title={t('操作尚未确认')}
            description={t(managementError)}
          />
        )}
        {managementSuccess && !detail.loading && !readError && (
          <p role="status">{t('操作已完成，已读取最新状态。')}</p>
        )}
        {detail.loading && <p role="status">{t('正在加载评估详情…')}</p>}
        {readError && (
          <EvaluationFeedback
            message={t(
              current
                ? t('{{value1}}；下方为上次读取的数据，请刷新后操作。', {
                    value1: t(readError),
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
        {current?.can_update && (
          <form
            className="evaluation-budget-form"
            onSubmit={(event) => {
              event.preventDefault()
              void manage('update')
            }}
          >
            <label htmlFor="evaluation-budget">{t('预算上限（USD）')}</label>
            <InputNumber
              id="evaluation-budget"
              min={0}
              value={budget === undefined ? current.budget_cap_usd : budget}
              onChange={(value) => setBudget(value)}
              disabled={busy || detail.loading || !!readError}
            />
            <Button
              htmlType="submit"
              disabled={
                busy ||
                detail.loading ||
                !!readError ||
                budget == null ||
                !Number.isFinite(budget) ||
                budget < 0
              }
            >
              {t('保存预算')}
            </Button>
          </form>
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
          {current?.can_pause && current.async_task_id && (
            <Button
              disabled={busy || detail.loading || !!readError}
              onClick={() => {
                void manage('pause')
              }}
            >
              {t('暂停任务')}
            </Button>
          )}
          {current?.can_resume && current.async_task_id && (
            <Button
              type="primary"
              disabled={busy || detail.loading || !!readError}
              onClick={() => {
                void manage('resume')
              }}
            >
              {t('恢复任务')}
            </Button>
          )}
          {current?.can_delete && (
            <Button
              danger
              disabled={busy || detail.loading || !!readError}
              onClick={() => setConfirmDelete(true)}
            >
              {t('删除评估')}
            </Button>
          )}
          {busy && <span role="status">{t('正在等待操作响应…')}</span>}
        </div>
        <Modal
          title={t('删除评估')}
          open={confirmDelete}
          onCancel={() => {
            if (!managementPending) setConfirmDelete(false)
          }}
          onOk={() => {
            void manage('delete')
          }}
          okText={t('确认删除')}
          cancelText={t('取消')}
          confirmLoading={managementPending}
          okButtonProps={{
            danger: true,
            disabled:
              busy || detail.loading || !!readError || !current?.can_delete,
          }}
          cancelButtonProps={{ disabled: managementPending }}
          closable={!managementPending}
          keyboard={!managementPending}
        >
          <p>{t('删除后无法恢复此评估及其关联文件。确认删除？')}</p>
        </Modal>
      </section>
    </section>
  )
}
