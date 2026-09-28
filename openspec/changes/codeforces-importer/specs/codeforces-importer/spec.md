# codeforces-importer Specification

## ADDED Requirements

### Requirement: Public Codeforces source

The system SHALL fetch Codeforces public problem metadata and statements without authentication or private tests, with contest, rating, tag, and limit filters and bounded transient retries.

#### Scenario: Filter a contest by rating and tag
- **WHEN** the importer receives contest 1234, rating 1200–1800, and tag dp
- **THEN** only matching non-interactive problems are requested for statement details

### Requirement: Standard Problem conversion

The importer SHALL map IDs, ratings, tags, stdin/stdout protocol, public samples, and source metadata into the existing Problem schema. Missing statements or samples SHALL be marked for manual completion.

#### Scenario: Convert a public sample
- **WHEN** a statement contains an input and output sample
- **THEN** the output Problem uses `codeforces_<contestId>_<index>`, the mapped difficulty, `main()` and a public stdin/stdout test case

### Requirement: Safe import CLI

The importer SHALL work through the shared import validation, duplicate, preview, confirmation, and atomic persistence flow.

#### Scenario: Rate limit or inaccessible statement
- **WHEN** Codeforces returns a transient error or a statement cannot be fetched
- **THEN** the import reports the failure or marks manual completion without inventing hidden tests
