import { Alert, Button } from 'antd'

export function EvaluationFeedback({
  message,
  retry,
}: {
  message: string
  retry?: () => void
}) {
  return (
    <Alert
      type="error"
      showIcon
      title={message}
      action={retry ? <Button onClick={retry}>重试</Button> : undefined}
    />
  )
}
