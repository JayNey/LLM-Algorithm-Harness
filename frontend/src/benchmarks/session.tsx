import type { AxiosInstance } from 'axios'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAuthStore } from '../store/auth.ts'
import { createBenchmarkClient } from './client.ts'
import type { BenchmarkClient } from './types.ts'

export interface BenchmarkSession {
  owner: string | null
  client: BenchmarkClient
}
const SessionContext = createContext<BenchmarkSession | null>(null)

export function BenchmarkSessionProvider({
  children,
}: {
  children: ReactNode
}) {
  const owner = useAuthStore((state) => state.session?.marker ?? null)
  return (
    <SessionScope key={owner ?? 'anonymous'} owner={owner}>
      {children}
    </SessionScope>
  )
}
function SessionScope({
  owner,
  children,
}: {
  owner: string | null
  children: ReactNode
}) {
  const [session] = useState<BenchmarkSession>(() => {
    // Auth exposes a narrow interface; the runtime object is the same unwrapped Axios instance.
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    return { owner, client: createBenchmarkClient(http) }
  })
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useBenchmarkSession(): BenchmarkSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error('基准功能需要会话 provider')
  return session
}
