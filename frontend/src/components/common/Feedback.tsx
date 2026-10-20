import { App, Button, Empty, Result, Skeleton } from 'antd'
import { Component, type ReactNode } from 'react'
export function Loading() {
  return (
    <div className="panel state-box" aria-busy="true" aria-label="正在加载页面">
      <p role="status">正在加载数据…</p>
      <Skeleton paragraph={{ rows: 6 }} />
    </div>
  )
}
export function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="panel state-box">
      <Empty
        description={
          <>
            <h3>还没有评估任务</h3>
            <p>选择模型与数据集，开始第一轮算法评估。</p>
          </>
        }
      >
        <Button type="primary" onClick={onCreate}>
          创建首个评估
        </Button>
      </Empty>
    </div>
  )
}
export function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="panel state-box" role="alert">
      <Result
        status="error"
        title="评估数据暂时无法加载"
        subTitle="连接超时（Mock）。你的配置已保留，可重试加载。"
        extra={
          <Button type="primary" onClick={onRetry}>
            重新加载
          </Button>
        }
      />
    </div>
  )
}
export class ErrorBoundary extends Component<
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
          title="页面暂时无法显示"
          subTitle="发生了页面错误，请重试。"
          extra={
            <Button onClick={() => this.setState({ failed: false })}>
              重试页面
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
            aria-label={`关闭${label}`}
            onClick={() => message.destroy(key)}
          >
            关闭
          </Button>
        </span>
      ),
    })
  }
  return (
    <div className="notification-actions" style={{ flexWrap: 'wrap' }}>
      {(
        [
          ['success', '成功提示'],
          ['error', '错误提示'],
          ['warning', '警告提示'],
          ['info', '信息提示'],
        ] as const
      ).map(([type, label]) => (
        <Button key={type} onClick={() => show(type, label)}>
          {label}
        </Button>
      ))}
    </div>
  )
}
