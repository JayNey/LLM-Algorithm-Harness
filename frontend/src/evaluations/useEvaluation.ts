import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClientError } from '../auth/http.ts'
import type { Evaluation, EvaluationClient } from './types.ts'

export function useEvaluation(
  client: EvaluationClient,
  evaluationId: string,
  owner: string | null,
) {
  const [attempt, setAttempt] = useState(0)
  const generation = useRef(0)
  const [snapshot, setSnapshot] = useState<{
    client: EvaluationClient
    evaluationId: string
    owner: string
    attempt: number
    data?: Evaluation
    error?: string
  }>()
  const reload = useCallback(() => setAttempt((value) => value + 1), [])
  useEffect(() => {
    const controller = new AbortController()
    const operation = ++generation.current
    if (owner && evaluationId) {
      const identity = { client, owner, evaluationId, attempt }
      void client.get(evaluationId, controller.signal).then(
        (data) => {
          if (!controller.signal.aborted && generation.current === operation)
            setSnapshot({ ...identity, data })
        },
        (error: unknown) => {
          if (controller.signal.aborted || generation.current !== operation)
            return
          const denied =
            error instanceof ApiClientError &&
            [403, 404].includes(error.status ?? 0)
          setSnapshot((previous) => ({
            ...identity,
            data:
              !denied &&
              previous?.client === client &&
              previous.owner === owner &&
              previous.evaluationId === evaluationId
                ? previous.data
                : undefined,
            error:
              error instanceof ApiClientError && error.message
                ? error.message
                : '加载任务失败，请重试',
          }))
        },
      )
    }
    return () => controller.abort()
  }, [client, evaluationId, owner, attempt])
  const current =
    !!owner &&
    snapshot?.owner === owner &&
    snapshot.client === client &&
    snapshot.evaluationId === evaluationId
  const loading = !current || snapshot.attempt !== attempt
  return {
    data: current ? snapshot.data : undefined,
    error: current && !loading ? snapshot.error : undefined,
    loading,
    reload,
  }
}
