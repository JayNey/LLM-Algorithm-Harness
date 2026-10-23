import { Alert, Button } from 'antd'

export function ExperimentFeedback({
  message,
  retry,
}: {
  message: string
  retry?: () => void
}) {
  return (
    <Alert
      role="alert"
      type="error"
      showIcon
      message={message}
      action={
        retry ? (
          <Button size="small" onClick={retry}>
            重试
          </Button>
        ) : undefined
      }
    />
  )
}
