import { useTranslation } from 'react-i18next'
import { t } from '../i18n/core.ts'
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
import { createExperimentClient } from './client.ts'
import {
  createExperimentCreationStore,
  type CreationState,
} from './runCreation.ts'
import type { ExperimentClient } from './types.ts'

export interface ExperimentSession {
  owner: string | null
  client: ExperimentClient
  creationStore: StoreApi<CreationState>
}
const useCommittedEffect =
  typeof window === 'undefined' ? useEffect : useLayoutEffect
const SessionContext = createContext<ExperimentSession | null>(null)

export function ExperimentSessionProvider({
  children,
}: {
  children: ReactNode
}) {
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

  const navigate = useNavigate()
  const location = useLocation()
  const [navigation] = useState(() =>
    createCreatedNavigation(location.pathname, navigate),
  )
  useCommittedEffect(() => {
    navigation.update(location.pathname, navigate)
  }, [location.pathname, navigate, navigation])
  const [scope] = useState(() => {
    let active = true
    // Auth exposes a narrow interface; the runtime object is the same unwrapped Axios instance.
    const http = useAuthStore.getState().httpClient() as AxiosInstance
    const client = createExperimentClient(http)
    const creationStore = createExperimentCreationStore({
      client,
      readOwner: () =>
        active ? (useAuthStore.getState().session?.marker ?? null) : null,
      onCreated: navigation.onCreated,
    })
    return {
      session: { owner, client, creationStore },
      activate() {
        active = true
      },
      deactivate() {
        // StrictMode 重挂同一实例时不抹掉子 effect 的草稿写入。
        active = false
        queueMicrotask(() => {
          if (!active) creationStore.getState().reset(null)
        })
      },
    }
  })
  useCommittedEffect(() => {
    scope.activate()
    return scope.deactivate
  }, [scope])
  return (
    <SessionContext.Provider value={scope.session}>
      {children}
    </SessionContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useExperimentSession(): ExperimentSession {
  const session = useContext(SessionContext)
  if (!session) throw new Error(t('实验功能需要会话 provider'))
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
    onCreated(experimentId: string) {
      if (path === '/experiments/new') {
        void navigate(`/experiments/${encodeURIComponent(experimentId)}`, {
          replace: true,
        })
      }
    },
  }
}
