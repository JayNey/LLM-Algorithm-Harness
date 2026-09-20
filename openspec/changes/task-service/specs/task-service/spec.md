# task-service Specification

## ADDED Requirements

### Requirement: Persistent task lifecycle

The system SHALL expose a local task record with a stable run_id, queued/running/completed/failed/cancelled states, per-unit strategy/problem/repetition identity, and ordered structured progress events.

#### Scenario: Queryable task progress
- **WHEN** a task is created and units are dispatched
- **THEN** each lifecycle transition is persisted with sequence, unit identity, completed count, and total count

### Requirement: Atomic persistence and safe resume

The system SHALL atomically persist task state and SHALL reject resume when the configuration or dataset fingerprint differs. Resume SHALL skip confirmed terminal units and requeue unfinished or uncertain units.

#### Scenario: Fingerprint mismatch
- **WHEN** a caller resumes with a different configuration or dataset fingerprint
- **THEN** the service fails before dispatching any unit

### Requirement: Bounded concurrency and cancellation

The system SHALL never dispatch more than max_workers units concurrently. A cancellation request SHALL stop new dispatches, mark queued units cancelled, and mark in-flight units uncertain without claiming exactly-once external API execution.

#### Scenario: Cancel an in-flight model call
- **WHEN** cancellation arrives while a worker is running
- **THEN** the task becomes cancelled, queued work is not started, and the in-flight unit is recorded as uncertain

### Requirement: Shared CLI execution path

The existing CLI SHALL use the task service for evaluation and SHALL preserve the direct Harness API for existing callers.

#### Scenario: Run and resume from CLI
- **WHEN** the CLI is run with `--run-id` and later `--resume --run-id`
- **THEN** both invocations use the same persisted task record and do not duplicate confirmed completed units
