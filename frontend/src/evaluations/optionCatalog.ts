import { useCallback } from 'react'
import type { AxiosInstance } from 'axios'
import { useAuthStore } from '../store/auth.ts'
import { createEvaluationClient } from './client.ts'
import type { EvaluationOptions, ModelOptions } from './types.ts'
import { useResource } from '../hooks/useResource.ts'

export function splitStrategyText(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function joinStrategyTags(values: string[]): string {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))].join(
    ', ',
  )
}

export function effectiveApiKey(
  modelKeyId: string,
  defaultKeyId: string,
): string {
  return modelKeyId.trim() || defaultKeyId.trim()
}

function optionsHttpClient(): AxiosInstance {
  return useAuthStore.getState().httpClient() as AxiosInstance
}

export function useEvaluationOptions(): {
  data?: EvaluationOptions
  error?: string
  loading: boolean
  retry: () => void
} {
  const load = useCallback(
    (signal: AbortSignal) =>
      createEvaluationClient(optionsHttpClient()).options(signal),
    [],
  )
  return useResource(load)
}

export function useModelOptions(apiKeyId: string): {
  data?: ModelOptions | null
  error?: string
  loading: boolean
  retry: () => void
} {
  const load = useCallback(
    async (signal: AbortSignal) => {
      if (!apiKeyId.trim()) return null
      return createEvaluationClient(optionsHttpClient()).models(
        apiKeyId,
        signal,
      )
    },
    [apiKeyId],
  )
  return useResource(load)
}
