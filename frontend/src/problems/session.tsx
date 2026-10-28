import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import type { AxiosInstance } from 'axios'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAuthStore } from '../store/auth.ts'
import { createProblemClient } from './client.ts'
import type { ProblemClient } from './types.ts'

export interface ProblemSession {
  owner: string | null
  client: ProblemClient
}
const SessionContext = createContext<ProblemSession | null>(null)

export function ProblemSessionProvider({ children }: { children: ReactNode }) {
  useTranslation()

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
  useTranslation()

  const [session] = useState<ProblemSession>(() => {
    // Auth exposes a narrow interface; the runtime object is the same unwrapped Axios instance.
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    return { owner, client: createProblemClient(http) }
  })
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProblemSession(): ProblemSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error(t('题目功能需要会话 provider'))
  return session
}
