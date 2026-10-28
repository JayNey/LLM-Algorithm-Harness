import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import { Alert, Button } from 'antd'

export function ExperimentFeedback({
  message,
  retry,
}: {
  message: string
  retry?: () => void
}) {
  useTranslation()

  return (
    <Alert
      role="alert"
      type="error"
      showIcon
      message={t(message)}
      action={
        retry ? (
          <Button size="small" onClick={retry}>
            {t('重试')}
          </Button>
        ) : undefined
      }
    />
  )
}
