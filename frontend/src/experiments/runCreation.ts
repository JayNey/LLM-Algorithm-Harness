import { createStore, type StoreApi } from 'zustand/vanilla'
import { ApiClientError } from '../auth/http.ts'
import type {
  CreatePayload,
  ExperimentClient,
  ExperimentDraft,
} from './types.ts'
import { createExperimentPayload } from './validation.ts'

export type CreationPhase =
  'editing' | 'creating' | 'created' | 'create-unknown'
export interface CreationState {
  owner: string | null
  draft: ExperimentDraft
  phase: CreationPhase
  experimentId: string | null
  error: ApiClientError | null
  setDraft(patch: Partial<ExperimentDraft>): void
  submit(): Promise<void>
  reset(owner: string | null): void
}
export interface CreationDeps {
  client: ExperimentClient
  readOwner(): string | null
  onCreated?(experimentId: string): void
}

function emptyDraft(): ExperimentDraft {
  return {
    name: '',
    dataset_path: '',
    api_key_id: '',
    models: [{ model: '', temperature: '', api_key_id: '' }],
    strategies: [{ name: '', max_iterations: '', temperature: '' }],
    repeats: '1',
    execution: 'serial',
    max_workers: '4',
    budget_kind: 'none',
    budget_value: '',
  }
}

function asError(error: unknown): ApiClientError {
  return error instanceof ApiClientError
    ? error
    : new ApiClientError('实验请求失败，请核对任务状态')
}

export function createExperimentCreationStore(
  deps: CreationDeps,
): StoreApi<CreationState> {
  let operation = 0
  let active: Promise<void> | null = null
  return createStore<CreationState>((set, get) => {
    function owns(owner: string | null): owner is string {
      return (
        owner !== null && get().owner === owner && deps.readOwner() === owner
      )
    }
    function current(owner: string, id: number): boolean {
      return owns(owner) && operation === id
    }
    function run(
      owner: string,
      phase: CreationPhase,
      action: (id: number) => Promise<void>,
    ): Promise<void> {
      const id = ++operation
      const task = Promise.resolve().then(async () => {
        if (!current(owner, id)) return
        try {
          await action(id)
        } finally {
          if (operation === id) active = null
        }
      })
      active = task
      set({ phase, error: null })
      return task
    }
    return {
      owner: deps.readOwner(),
      draft: emptyDraft(),
      phase: 'editing',
      experimentId: null,
      error: null,
      setDraft(patch) {
        const state = get()
        if (!owns(state.owner) || state.phase !== 'editing') return
        set({
          draft: {
            ...state.draft,
            ...patch,
            models: patch.models
              ? patch.models.map((model) => ({ ...model }))
              : state.draft.models.map((model) => ({ ...model })),
            strategies: patch.strategies
              ? patch.strategies.map((strategy) => ({ ...strategy }))
              : state.draft.strategies.map((strategy) => ({ ...strategy })),
          },
          error: null,
        })
      },
      submit() {
        const { owner, phase, draft } = get()
        if (!owns(owner)) return Promise.resolve()
        if (active) return active
        if (phase !== 'editing') return Promise.resolve()
        let payload: CreatePayload
        try {
          payload = createExperimentPayload(draft)
        } catch (error) {
          set({ error: asError(error) })
          return Promise.resolve()
        }
        return run(owner, 'creating', async (id) => {
          try {
            if (!current(owner, id)) return
            const created = await deps.client.create(payload)
            if (!current(owner, id)) return
            set({ phase: 'created', experimentId: created.id })
            if (!current(owner, id)) return
            deps.onCreated?.(created.id)
          } catch (error) {
            if (!current(owner, id)) return
            const failure = asError(error)
            // 已确认拿到 ID 后不再回到编辑态（避免重复创建）。
            const rejected =
              failure.status !== undefined &&
              failure.status >= 400 &&
              failure.status < 500 &&
              failure.status !== 408
            set({
              phase:
                get().experimentId !== null
                  ? 'created'
                  : rejected
                    ? 'editing'
                    : 'create-unknown',
              error: failure,
            })
          }
        })
      },
      reset(owner) {
        operation++
        active = null
        set({
          owner,
          draft: emptyDraft(),
          phase: 'editing',
          experimentId: null,
          error: null,
        })
      },
    }
  })
}
