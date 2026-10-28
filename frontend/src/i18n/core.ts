import { initReactI18next } from 'react-i18next'
import { createInstance, type i18n as I18n } from 'i18next'
import zhCN from './zh-CN.ts'
import enUS from './en-US.ts'

export type Language = 'zh-CN' | 'en-US'
export type LanguageStorage = Pick<Storage, 'getItem' | 'setItem'>
export const languageStorageKey = 'llm-harness-language'
export const isLanguage = (value: unknown): value is Language =>
  value === 'zh-CN' || value === 'en-US'

export function browserStorage(): LanguageStorage | undefined {
  if (typeof window === 'undefined') return undefined
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}

export function createLocalization(
  options: { storage?: LanguageStorage } = {},
): I18n {
  const storage = options.storage ?? browserStorage()
  let language: Language = 'zh-CN'
  try {
    const saved = storage?.getItem(languageStorageKey)
    if (isLanguage(saved)) language = saved
  } catch {
    // Storage access is optional; the current session remains usable.
  }
  const instance = createInstance()
  void instance.init({
    lng: language,
    supportedLngs: ['zh-CN', 'en-US'],
    fallbackLng: 'zh-CN',
    resources: {
      'zh-CN': { translation: zhCN },
      'en-US': { translation: enUS },
    },
    keySeparator: false,
    nsSeparator: false,
    initAsync: false,
    interpolation: { escapeValue: false },
  })
  instance.on('languageChanged', (value) => {
    try {
      storage?.setItem(languageStorageKey, value)
    } catch {
      // Keep the in-memory selection when persistence is blocked.
    }
  })
  const changeLanguage = instance.changeLanguage.bind(instance)
  instance.changeLanguage = (value, callback) =>
    isLanguage(value)
      ? changeLanguage(value, callback)
      : Promise.resolve(instance.t.bind(instance))
  return instance
}

export const i18n = createLocalization()
initReactI18next.init(i18n)
// Stable function identity keeps language changes out of request dependencies.
export const t = (
  key: string | null | undefined,
  values?: Record<string, unknown>,
): string => (key ? i18n.t(key, values ?? {}) : '')
export const currentLanguage = (): Language =>
  i18n.language === 'en-US' ? 'en-US' : 'zh-CN'
