import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'

const rootDir = fileURLToPath(new URL('.', import.meta.url))
const requiredEnvKeys = ['VITE_API_BASE_URL', 'VITE_WS_URL', 'VITE_APP_NAME']

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, rootDir, 'VITE_')
  const missing = requiredEnvKeys.filter((key) => !env[key]?.trim())
  if (missing.length > 0) {
    throw new Error(`缺少环境变量: ${missing.join(', ')}`)
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': resolve(rootDir, 'src'),
      },
    },
  }
})
