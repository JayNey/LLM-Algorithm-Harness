import type { AxiosInstance } from 'axios'
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from 'react'
import {
  useLocation,
  useNavigate,
  type NavigateFunction,
} from 'react-router-dom'
import type { StoreApi } from 'zustand/vanilla'
import { useAuthStore } from '../store/auth.ts'
import { createEvaluationClient } from './client.ts'
import { createCreationStore, type CreationState } from './creation.ts'
import type { EvaluationClient } from './types.ts'

export interface EvaluationSession {
  owner: string | null
  client: EvaluationClient
  creationStore: StoreApi<CreationState>
}
const useCommittedEffect =
  typeof window === 'undefined' ? useEffect : useLayoutEffect
const SessionContext = createContext<EvaluationSession | null>(null)

export function EvaluationSessionProvider({
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
  const navigate = useNavigate()
  const location = useLocation()
  const [navigation] = useState(() =>
    createCreatedNavigation(location.pathname, navigate),
  )
  useCommittedEffect(() => {
    navigation.update(location.pathname, navigate)
  }, [location.pathname, navigate, navigation])
  const [session] = useState(() => {
    // Auth exposes a narrow interface; the runtime object is the same unwrapped Axios instance.
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    const client = createEvaluationClient(http)
    const creationStore = createCreationStore({
      client,
      readOwner: () => useAuthStore.getState().session?.marker ?? null,
      onCreated: navigation.onCreated,
    })
    return { owner, client, creationStore }
  })
  useEffect(() => {
    // React StrictMode replays effect setup/cleanup. Restore the same owner on setup.
    if (session.creationStore.getState().owner !== owner)
      session.creationStore.getState().reset(owner)
    return () => session.creationStore.getState().reset(null)
  }, [owner, session])
  return (
    <SessionContext.Provider value={session}>
      {children}
    </SessionContext.Provider>
  )
}
// eslint-disable-next-line react-refresh/only-export-components
export function useEvaluationSession(): EvaluationSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error('评估功能需要会话 provider')
  return session
}

// eslint-disable-next-line react-refresh/only-export-components
export function createCreatedNavigation(
  path: string,
  navigate: NavigateFunction,
) {
  return {
    update(nextPath: string, nextNavigate: NavigateFunction) {
      path = nextPath
      navigate = nextNavigate
    },
    onCreated(evaluationId: string) {
      if (path === '/evaluations/new') {
        void navigate(`/evaluations/${encodeURIComponent(evaluationId)}`, {
          replace: true,
        })
      }
    },
  }
}
