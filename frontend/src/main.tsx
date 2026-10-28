import { LocaleProvider } from '@/i18n/LocaleProvider.tsx'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { readViteEnv } from '@/config/env.ts'
import { applyColorScheme, useUiStore } from '@/store/ui.ts'
import './index.css'
import App from './App.tsx'

document.title = readViteEnv().appName
function applyAppearance() {
  const { colorScheme, appearanceVariant } = useUiStore.getState()
  applyColorScheme(colorScheme)
  document.documentElement.dataset.design = appearanceVariant
}
applyAppearance()
const unsubscribeAppearance = useUiStore.subscribe(applyAppearance)
const media = matchMedia('(prefers-color-scheme: dark)')
const updateSystemTheme = () =>
  useUiStore.getState().setSystemDark(media.matches)
media.addEventListener('change', updateSystemTheme)
if (import.meta.hot)
  import.meta.hot.dispose(() => {
    unsubscribeAppearance()
    media.removeEventListener('change', updateSystemTheme)
  })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </StrictMode>,
)
