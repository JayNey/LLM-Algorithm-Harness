import { useTranslation } from 'react-i18next'
import { t } from '../../i18n/core.ts'
import { App, Button, Empty, Result, Skeleton } from 'antd'
import { Component, type ReactNode } from 'react'
export function Loading() {
  useTranslation()

  return (
    <div
      className="panel state-box"
      aria-busy="true"
      aria-label={t('正在加载页面')}
    >
      <p role="status">{t('正在加载数据…')}</p>
      <Skeleton paragraph={{ rows: 6 }} />
    </div>
  )
}
export function EmptyState({ onCreate }: { onCreate: () => void }) {
  useTranslation()

  return (
    <div className="panel state-box">
      <Empty
        description={
          <>
            <h3>{t('还没有评估任务')}</h3>
            <p>{t('选择模型与数据集，开始第一轮算法评估。')}</p>
          </>
        }
      >
        <Button type="primary" onClick={onCreate}>
          {t('创建首个评估')}
        </Button>
      </Empty>
    </div>
  )
}
export function ErrorState({ onRetry }: { onRetry: () => void }) {
  useTranslation()

  return (
    <div className="panel state-box" role="alert">
      <Result
        status="error"
        title={t('评估数据暂时无法加载')}
        subTitle={t('连接超时（Mock）。你的配置已保留，可重试加载。')}
        extra={
          <Button type="primary" onClick={onRetry}>
            {t('重新加载')}
          </Button>
        }
      />
    </div>
  )
}
class PageErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <div role="alert">
        <Result
          status="error"
          title={t('页面暂时无法显示')}
          subTitle={t('发生了页面错误，请重试。')}
          extra={
            <Button onClick={() => this.setState({ failed: false })}>
              {t('重试页面')}
            </Button>
          }
        />
      </div>
    ) : (
      this.props.children
    )
  }
}
export function ToastExamples() {
  useTranslation()

  const { message } = App.useApp()
  function show(type: 'success' | 'error' | 'warning' | 'info', label: string) {
    const key = `feedback-${type}`
    void message.open({
      key,
      type,
      duration: 4,
      content: (
        <span>
          {label} · Mock{' '}
          <Button
            type="text"
            size="small"
            aria-label={t('关闭{{value1}}', { value1: label })}
            onClick={() => message.destroy(key)}
          >
            {t('关闭')}
          </Button>
        </span>
      ),
    })
  }
  return (
    <div className="notification-actions" style={{ flexWrap: 'wrap' }}>
      {(
        [
          ['success', t('成功提示')],
          ['error', t('错误提示')],
          ['warning', t('警告提示')],
          ['info', t('信息提示')],
        ] as const
      ).map(([type, label]) => (
        <Button key={type} onClick={() => show(type, label)}>
          {label}
        </Button>
      ))}
    </div>
  )
}

export function ErrorBoundary({ children }: { children: ReactNode }) {
  useTranslation()
  return <PageErrorBoundary>{children}</PageErrorBoundary>
}
