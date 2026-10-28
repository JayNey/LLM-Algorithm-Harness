import { t } from '../i18n/core.ts'
import { AutoComplete, Button, Select, Spin } from 'antd'
import {
  joinStrategyTags,
  splitStrategyText,
  useEvaluationOptions,
  useModelOptions,
} from './optionCatalog.ts'

function DirectoryHint({
  message,
  onRetry,
  retryLabel,
}: {
  message: string
  onRetry?: () => void
  retryLabel?: string
}) {
  return (
    <small role="note">
      {message}
      {onRetry && (
        <Button
          type="link"
          size="small"
          aria-label={retryLabel}
          onClick={onRetry}
        >
          {t('重试')}
        </Button>
      )}
    </small>
  )
}

function catalogNotFound(loading: boolean, emptyText: string) {
  if (loading) return <Spin size="small" />
  return <span>{emptyText}</span>
}

export function ModelNameField({
  value,
  onChange,
  apiKeyId,
  disabled,
  ariaLabel,
}: {
  value: string
  onChange: (value: string) => void
  apiKeyId: string
  disabled?: boolean
  ariaLabel: string
}) {
  const models = useModelOptions(apiKeyId)
  return (
    <>
      <AutoComplete
        aria-label={ariaLabel}
        value={value}
        placeholder={t('模型名，如 model-a')}
        options={(models.data?.models ?? []).map((name) => ({ value: name }))}
        notFoundContent={
          models.loading ? (
            <Spin size="small" />
          ) : !apiKeyId.trim() ? (
            <span>{t('请选择可用密钥')}</span>
          ) : (
            <span>{t('目录为空，可手动输入')}</span>
          )
        }
        onChange={(next) => onChange(next)}
        disabled={disabled}
      />
      {models.error && (
        <DirectoryHint
          message={t('模型目录加载失败，可手动输入')}
          onRetry={models.retry}
          retryLabel={t('重试加载模型目录')}
        />
      )}
      {!models.error && models.data && !models.data.complete && (
        <DirectoryHint message={t('模型目录可能不完整，可手动输入')} />
      )}
    </>
  )
}

export function StrategyNameField({
  value,
  onChange,
  disabled,
  ariaLabel,
}: {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  ariaLabel: string
}) {
  const options = useEvaluationOptions()
  return (
    <>
      <AutoComplete
        aria-label={ariaLabel}
        value={value}
        placeholder={t('策略名，如 vanilla')}
        options={(options.data?.strategies ?? []).map((strategy) => ({
          value: strategy.name,
        }))}
        notFoundContent={catalogNotFound(
          options.loading,
          t('目录为空，可手动输入'),
        )}
        onChange={(next) => onChange(next)}
        disabled={disabled}
      />
      {options.error && (
        <DirectoryHint
          message={t('策略目录加载失败，可手动输入')}
          onRetry={options.retry}
          retryLabel={t('重试加载策略目录')}
        />
      )}
    </>
  )
}

export function StrategyTagsField({
  value,
  onChange,
  disabled,
  ariaLabel,
}: {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  ariaLabel: string
}) {
  const options = useEvaluationOptions()
  return (
    <>
      <Select
        mode="tags"
        aria-label={ariaLabel}
        value={splitStrategyText(value)}
        options={(options.data?.strategies ?? []).map((strategy) => ({
          value: strategy.name,
        }))}
        notFoundContent={catalogNotFound(
          options.loading,
          t('目录为空，可手动输入'),
        )}
        tokenSeparators={[',']}
        onChange={(next: string[]) => onChange(joinStrategyTags(next))}
        disabled={disabled}
      />
      {options.error && (
        <DirectoryHint
          message={t('策略目录加载失败，可手动输入')}
          onRetry={options.retry}
          retryLabel={t('重试加载策略目录')}
        />
      )}
    </>
  )
}
