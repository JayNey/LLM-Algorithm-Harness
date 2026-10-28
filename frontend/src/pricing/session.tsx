import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
import type { AxiosInstance } from 'axios'
import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAuthStore } from '../store/auth.ts'
import { createPricingClient } from './client.ts'
import type { PricingClient } from './types.ts'

export interface PricingSession {
  owner: string | null
  client: PricingClient
}
const SessionContext = createContext<PricingSession | null>(null)

export function PricingSessionProvider({ children }: { children: ReactNode }) {
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

  const [session] = useState<PricingSession>(() => {
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    return { owner, client: createPricingClient(http) }
  })
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePricingSession(): PricingSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error(t('定价功能需要会话 provider'))
  return session
}
