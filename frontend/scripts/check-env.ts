import { readFileSync } from 'node:fs'
import { readAppEnv, parseEnvFile } from '../src/config/env.ts'

const modes = ['development', 'test', 'production'] as const

for (const mode of modes) {
  const text = readFileSync(new URL(`../.env.${mode}`, import.meta.url), 'utf8')
  const env = readAppEnv(parseEnvFile(text))
  if (!env.apiBaseUrl || !env.wsUrl || !env.appName) {
    throw new Error(`${mode} 环境文件缺少必填值`)
  }
  if (mode === 'test' && !env.featureFlags.has('test-mode')) {
    throw new Error('test 模式应读到功能开关 test-mode')
  }
  if (mode !== 'test' && env.featureFlags.size !== 0) {
    throw new Error(`${mode} 模式不应带测试功能开关`)
  }
}

let rejected = false
try {
  readAppEnv({
    VITE_WS_URL: 'ws://localhost:8000/api/v1/ws/progress',
    VITE_APP_NAME: 'LLM Algorithm Harness',
  })
} catch (error) {
  rejected =
    error instanceof Error && error.message.includes('VITE_API_BASE_URL')
}
if (!rejected) {
  throw new Error('缺失 VITE_API_BASE_URL 时必须失败')
}

console.log('env ok')
