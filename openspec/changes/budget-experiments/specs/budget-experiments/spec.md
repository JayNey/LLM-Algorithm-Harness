# budget-experiments Specification

## ADDED Requirements

### Requirement: Equal per-problem budgets

The system SHALL apply the same configured call, token, and elapsed-time limits to each model/strategy/problem/repetition unit. It SHALL reject a new request after a reached limit, record actual consumption and stop reason, and label provider token/time limits as observed rather than hard guarantees.

#### Scenario: Call budget exhausted
- **WHEN** an iterative strategy requests another call after max_calls is reached
- **THEN** no further provider call is made and the result records budget_exhausted

#### Scenario: Unknown token usage
- **WHEN** a provider omits usage under a token budget
- **THEN** the experiment marks usage unknown and blocks the next call rather than treating it as free

### Requirement: Reconstructable experiment identity

The system SHALL identify each unit by model, strategy, problem, and repetition, and record configuration, dataset, and code version fingerprints. Resume SHALL reject changed config or dataset and skip confirmed completed units.

#### Scenario: Dataset changed before resume
- **WHEN** the dataset content differs from the original run
- **THEN** resume fails before another model request

### Requirement: Honest comparison and cost

The system SHALL distinguish public sample validation from independent hidden evaluation, report failure categories and repair rate with denominators, and group known time and token consumption by difficulty and tag. It SHALL calculate cost from configured input/output prices with source/date, and represent unknown price or usage as unknown.

#### Scenario: Sample overfitting and API failure
- **WHEN** a fixture includes a correct solution, a sample-only pass that fails hidden tests, and an API failure
- **THEN** formal and sample rates, failure counts, and cost unknown status match the fixture exactly

### Requirement: Portable experiment reports

The system SHALL export JSON, CSV, and readable Markdown reports and SHALL state that remote generation is not bitwise reproducible even when inputs are fixed.

#### Scenario: Repeated fixed configuration
- **WHEN** an experiment has more than one repetition
- **THEN** the report retains each repetition and summarizes the observed formal pass-rate range
