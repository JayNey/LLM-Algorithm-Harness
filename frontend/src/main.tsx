import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { readViteEnv } from '@/config/env.ts'
import { applyColorScheme, useUiStore } from '@/store/ui.ts'
import './index.css'
import App from './App.tsx'

document.title = readViteEnv().appName
applyColorScheme(useUiStore.getState().colorScheme)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
