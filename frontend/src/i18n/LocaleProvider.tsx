import { useEffect, type ReactNode } from 'react'
import { ConfigProvider } from 'antd'
import enUS from 'antd/locale/en_US'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { I18nextProvider, useTranslation } from 'react-i18next'
import { currentLanguage, i18n, isLanguage, t } from './core.ts'

function LanguageEnvironment({ children }: { children: ReactNode }) {
  const { i18n: instance } = useTranslation()
  const language = currentLanguage()
  useEffect(() => {
    const apply = () => {
      document.documentElement.lang = currentLanguage()
      dayjs.locale(currentLanguage() === 'zh-CN' ? 'zh-cn' : 'en')
    }
    apply()
    instance.on('languageChanged', apply)
    return () => {
      instance.off('languageChanged', apply)
    }
  }, [instance])
  return (
    <ConfigProvider locale={language === 'zh-CN' ? zhCN : enUS}>
      {children}
    </ConfigProvider>
  )
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={i18n}>
      <LanguageEnvironment>{children}</LanguageEnvironment>
    </I18nextProvider>
  )
}

export function LanguageSelect() {
  useTranslation()
  return (
    <label className="language-control">
      <span>{t('语言')}</span>
      <select
        aria-label={t('界面语言')}
        value={currentLanguage()}
        onChange={(event) => {
          const value = event.target.value
          if (isLanguage(value)) void i18n.changeLanguage(value)
        }}
      >
        <option value="zh-CN" lang="zh-CN">
          简体中文
        </option>
        <option value="en-US" lang="en-US">
          English
        </option>
      </select>
    </label>
  )
}
