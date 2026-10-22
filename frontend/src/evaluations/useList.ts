import { useEffect, useRef, useState } from 'react'
import { ApiClientError } from '../auth/http.ts'
import type { ApiPage, ListQuery } from './types.ts'

type Loader<T> = (query: ListQuery, signal: AbortSignal) => Promise<ApiPage<T>>
export interface ListState<T> {
  status: 'loading' | 'ready' | 'error'
  data?: ApiPage<T>
  error?: string
  reload: () => void
}

export function useList<T>(
  load: Loader<T>,
  query: ListQuery,
  owner: string,
): ListState<T> {
  const [attempt, setAttempt] = useState(0)
  const generation = useRef(0)
  const { status, limit, offset } = query
  const [snapshot, setSnapshot] = useState<{
    owner: string
    load: Loader<T>
    status: string | undefined
    limit: number
    offset: number
    attempt: number
    data?: ApiPage<T>
    error?: string
  }>()
  useEffect(() => {
    const controller = new AbortController()
    const operation = ++generation.current
    if (owner) {
      void (async () => {
        const identity = { owner, load, status, limit, offset, attempt }
        try {
          const data = await load(
            { ...(status ? { status } : {}), limit, offset },
            controller.signal,
          )
          if (!controller.signal.aborted && operation === generation.current)
            setSnapshot({ ...identity, data })
        } catch (error: unknown) {
          if (!controller.signal.aborted && operation === generation.current)
            setSnapshot({
              ...identity,
              error:
                error instanceof ApiClientError && error.message
                  ? error.message
                  : '加载失败，请重试',
            })
        }
      })()
    }
    return () => {
      controller.abort()
    }
  }, [load, owner, status, limit, offset, attempt])

  // Hide an old page during render, before cleanup/new effects have run.
  const current =
    !!owner &&
    snapshot?.owner === owner &&
    snapshot.load === load &&
    snapshot.status === status &&
    snapshot.limit === limit &&
    snapshot.offset === offset &&
    snapshot.attempt === attempt
  return {
    status: !current
      ? 'loading'
      : snapshot.error !== undefined
        ? 'error'
        : 'ready',
    data: current ? snapshot.data : undefined,
    error: current ? snapshot.error : undefined,
    reload: () => setAttempt((value) => value + 1),
  }
}
