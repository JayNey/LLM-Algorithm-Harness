import { t } from '../i18n/core.ts'
import { create } from 'zustand'

export type ColorScheme = 'light' | 'dark'
export type ThemePreference = ColorScheme | 'system'
export type AppearanceVariant = 'orbit' | 'precision' | 'studio'
export const appearanceVariants = {
  orbit: {
    get name() {
      return t('深空控制台')
    },
    en: 'Orbit',
    get desc() {
      return t('运行、观测与恢复')
    },
  },
  precision: {
    get name() {
      return t('精密实验室')
    },
    en: 'Precision',
    get desc() {
      return t('基准、度量与比较')
    },
  },
  studio: {
    get name() {
      return t('石墨工作室')
    },
    en: 'Studio',
    get desc() {
      return t('实验、记录与迭代')
    },
  },
}
interface UiState {
  appearanceVariant: AppearanceVariant
  themePreference: ThemePreference
  themes: Record<AppearanceVariant, ThemePreference>
  colorScheme: ColorScheme
  systemDark: boolean
  sidebarCollapsed: boolean
  setAppearanceVariant: (variant: AppearanceVariant) => void
  setThemePreference: (preference: ThemePreference) => void
  setSystemDark: (dark: boolean) => void
  toggleColorScheme: () => void
  toggleSidebar: () => void
}
type PreferenceStorage = Pick<Storage, 'getItem' | 'setItem'>
const storageKey = 'llm-harness-ui'
const isVariant = (value: unknown): value is AppearanceVariant =>
  typeof value === 'string' && Object.hasOwn(appearanceVariants, value)
const isTheme = (value: unknown): value is ThemePreference =>
  value === 'light' || value === 'dark' || value === 'system'
const resolve = (preference: ThemePreference, dark: boolean): ColorScheme =>
  preference === 'system' ? (dark ? 'dark' : 'light') : preference
function browserStorage(): PreferenceStorage | undefined {
  if (typeof window === 'undefined') return undefined
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}
export function applyColorScheme(colorScheme: ColorScheme): void {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', colorScheme === 'dark')
  document.documentElement.dataset.theme = colorScheme
}
export function createUiStore(
  options: { storage?: PreferenceStorage; systemDark?: boolean } = {},
) {
  const storage = options.storage ?? browserStorage()
  const themes: Record<AppearanceVariant, ThemePreference> = {
    orbit: 'dark',
    precision: 'light',
    studio: 'light',
  }
  let appearanceVariant: AppearanceVariant = 'orbit'
  let sidebarCollapsed = false
  try {
    const saved = JSON.parse(storage?.getItem(storageKey) ?? 'null')
    if (saved && typeof saved === 'object') {
      if (isVariant(saved.appearanceVariant))
        appearanceVariant = saved.appearanceVariant
      sidebarCollapsed = saved.sidebarCollapsed === true
      for (const variant of Object.keys(themes) as AppearanceVariant[]) {
        if (isTheme(saved.themes?.[variant]))
          themes[variant] = saved.themes[variant]
      }
    } else if (typeof sessionStorage !== 'undefined') {
      const legacy = sessionStorage.getItem('llm-harness-color-scheme')
      if (isTheme(legacy)) themes.orbit = legacy
    }
  } catch {
    /* Browser storage is optional. */
  }
  const systemDark =
    options.systemDark ??
    (typeof matchMedia === 'function' &&
      matchMedia('(prefers-color-scheme: dark)').matches)
  const preference = themes[appearanceVariant]
  return create<UiState>((set, get) => {
    function update(patch: Partial<UiState>) {
      set(patch)
      const state = get()
      try {
        storage?.setItem(
          storageKey,
          JSON.stringify({
            appearanceVariant: state.appearanceVariant,
            themes: state.themes,
            sidebarCollapsed: state.sidebarCollapsed,
          }),
        )
      } catch {
        /* Keep in-memory preferences. */
      }
    }
    return {
      appearanceVariant,
      themes,
      themePreference: preference,
      systemDark,
      sidebarCollapsed,
      colorScheme: resolve(preference, systemDark),
      setAppearanceVariant(variant) {
        if (!isVariant(variant)) return
        const state = get()
        const themePreference = state.themes[variant]
        update({
          appearanceVariant: variant,
          themePreference,
          colorScheme: resolve(themePreference, state.systemDark),
        })
      },
      setThemePreference(themePreference) {
        if (!isTheme(themePreference)) return
        const state = get()
        update({
          themePreference,
          themes: {
            ...state.themes,
            [state.appearanceVariant]: themePreference,
          },
          colorScheme: resolve(themePreference, state.systemDark),
        })
      },
      setSystemDark(dark) {
        const state = get()
        set({
          systemDark: dark,
          colorScheme: resolve(state.themePreference, dark),
        })
      },
      toggleColorScheme() {
        get().setThemePreference(
          get().colorScheme === 'dark' ? 'light' : 'dark',
        )
      },
      toggleSidebar() {
        update({ sidebarCollapsed: !get().sidebarCollapsed })
      },
    }
  })
}
export const useUiStore = createUiStore()
