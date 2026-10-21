import { createStore, type StoreApi } from 'zustand/vanilla'
import { ApiClientError } from '../auth/http.ts'
import type { Draft, EvaluationClient } from './types.ts'
import { createPayload } from './validation.ts'

export type CreationPhase =
  | 'editing'
  | 'creating'
  | 'created'
  | 'starting'
  | 'queued'
  | 'start-error'
  | 'create-unknown'
export interface CreationState {
  owner: string | null
  draft: Draft
  phase: CreationPhase
  evaluationId: string | null
  error: ApiClientError | null
  setDraft(patch: Partial<Draft>): void
  submit(): Promise<void>
  retryStart(evaluationId: string): Promise<void>
  reset(owner: string | null): void
}
export interface CreationDeps {
  client: EvaluationClient
  readOwner(): string | null
  onCreated?(evaluationId: string): void
}
function emptyDraft(): Draft {
  return {
    api_key_id: '',
    model: '',
    problem_ids: [],
    strategy_names: [],
    budget_cap_usd: '',
  }
}
function asError(error: unknown): ApiClientError {
  return error instanceof ApiClientError
    ? error
    : new ApiClientError('评估请求失败，请核对任务状态')
}

export function createCreationStore(
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
    // Reserve before publishing state: even a synchronous subscriber shares this lock.
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
    async function start(owner: string, id: number, evaluationId: string) {
      if (!current(owner, id)) return
      set({ phase: 'starting' })
      if (!current(owner, id)) return
      try {
        await deps.client.start(evaluationId)
        if (!current(owner, id)) return
        set({ phase: 'queued', error: null })
      } catch (error) {
        if (!current(owner, id)) return
        set({ phase: 'start-error', error: asError(error) })
      }
    }
    return {
      owner: deps.readOwner(),
      draft: emptyDraft(),
      phase: 'editing',
      evaluationId: null,
      error: null,
      setDraft(patch) {
        const state = get()
        if (!owns(state.owner) || state.phase !== 'editing') return
        const next = { ...state.draft, ...patch }
        // A key change invalidates its model; an explicitly supplied new model is allowed.
        if (
          patch.api_key_id !== undefined &&
          patch.api_key_id !== state.draft.api_key_id &&
          patch.model === undefined
        )
          next.model = ''
        set({
          draft: {
            ...next,
            problem_ids: [...next.problem_ids],
            strategy_names: [...next.strategy_names],
          },
          error: null,
        })
      },
      submit() {
        const { owner, phase, draft } = get()
        if (!owns(owner)) return Promise.resolve()
        if (active) return active
        if (phase !== 'editing') return Promise.resolve()
        let payload
        try {
          payload = createPayload(draft)
        } catch (error) {
          set({ error: asError(error) })
          return Promise.resolve()
        }
        return run(owner, 'creating', async (id) => {
          try {
            if (!current(owner, id)) return
            const created = await deps.client.create(payload)
            if (!current(owner, id)) return
            set({ phase: 'created', evaluationId: created.evaluation_id })
            if (!current(owner, id)) return
            deps.onCreated?.(created.evaluation_id)
            if (!current(owner, id)) return
            await start(owner, id, created.evaluation_id)
          } catch (error) {
            if (!current(owner, id)) return
            const failure = asError(error)
            // A confirmed ID is never turned back into another create operation.
            if (get().evaluationId !== null) {
              set({ phase: 'start-error', error: failure })
              return
            }
            const rejected =
              failure.status !== undefined &&
              failure.status >= 400 &&
              failure.status < 500 &&
              failure.status !== 408
            set({
              phase: rejected ? 'editing' : 'create-unknown',
              error: failure,
            })
          }
        })
      },
      retryStart(evaluationId) {
        const { owner, phase } = get()
        if (!owns(owner)) return Promise.resolve()
        if (active) return active
        if (phase === 'create-unknown' || !evaluationId.trim())
          return Promise.resolve()
        return run(owner, 'created', async (id) => {
          if (!current(owner, id)) return
          set({ evaluationId })
          if (!current(owner, id)) return
          try {
            const evaluation = await deps.client.get(evaluationId)
            if (!current(owner, id)) return
            if (!evaluation.can_start) {
              set({ phase: 'queued', error: null })
              return
            }
            await start(owner, id, evaluationId)
          } catch (error) {
            if (!current(owner, id)) return
            set({ phase: 'start-error', error: asError(error) })
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
          evaluationId: null,
          error: null,
        })
      },
    }
  })
}
