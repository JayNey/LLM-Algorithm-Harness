import { useTranslation } from 'react-i18next'
import { useRef, useState } from 'react'
import { t } from '../i18n/core.ts'
import { Alert, Button, Modal, type ButtonProps } from 'antd'

export function CancelExperimentButton({
  name,
  size,
  label,
  disabled,
  onConfirm,
}: {
  name: string
  size?: ButtonProps['size']
  label?: string
  disabled: boolean
  onConfirm: () => Promise<void>
}) {
  useTranslation()
  const [open, setOpen] = useState(false)
  const submitted = useRef(false)

  async function confirm() {
    if (!open || disabled || submitted.current) return
    submitted.current = true
    try {
      await onConfirm()
    } finally {
      setOpen(false)
    }
  }

  return (
    <>
      <Button
        aria-label={label}
        aria-haspopup="dialog"
        size={size}
        disabled={disabled}
        onClick={() => {
          submitted.current = false
          setOpen(true)
        }}
      >
        {t('取消运行')}
      </Button>
      <Modal
        title={t('取消运行')}
        open={open}
        onCancel={() => {
          if (!submitted.current) setOpen(false)
        }}
        onOk={() => void confirm()}
        okText={t('确认取消')}
        cancelText={t('返回')}
        confirmLoading={disabled}
        okButtonProps={{ danger: true }}
        cancelButtonProps={{ disabled }}
        closable={!disabled}
        keyboard={!disabled}
        mask={{ closable: false }}
      >
        <p>{t('确认取消实验「{{value1}}」？', { value1: name })}</p>
      </Modal>
    </>
  )
}

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
