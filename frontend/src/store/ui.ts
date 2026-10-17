import { create } from 'zustand'

const storageKey = 'llm-harness-color-scheme'

export type ColorScheme = 'light' | 'dark'

function readColorScheme(): ColorScheme {
  if (typeof sessionStorage === 'undefined') {
    return 'light'
  }
  return sessionStorage.getItem(storageKey) === 'dark' ? 'dark' : 'light'
}

export function applyColorScheme(colorScheme: ColorScheme): void {
  document.documentElement.classList.toggle('dark', colorScheme === 'dark')
}

interface UiState {
  colorScheme: ColorScheme
  toggleColorScheme: () => void
}

export const useUiStore = create<UiState>((set, get) => ({
  colorScheme: readColorScheme(),
  toggleColorScheme: () => {
    const colorScheme: ColorScheme =
      get().colorScheme === 'dark' ? 'light' : 'dark'
    sessionStorage.setItem(storageKey, colorScheme)
    applyColorScheme(colorScheme)
    set({ colorScheme })
  },
}))
