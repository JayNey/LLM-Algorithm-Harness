# problem-recommender Specification

## ADDED Requirements

### Requirement: Weakness analysis

The system SHALL read historical evaluation results and compute failure rate, failed count, total count, and problem count for difficulty, tag, tag-combination, and difficulty-tag groups. It SHALL include groups meeting the configured failure threshold and minimum sample count in the weakness report.

#### Scenario: High-failure dynamic programming group
- **WHEN** two historical DP records fail
- **THEN** the DP group is ranked with failure rate 100%, failed count 2, and total count 2

### Requirement: Unevaluated recommendations

The system SHALL recommend only problems present in the selected dataset whose problem_id has not appeared in historical results. Candidates SHALL be ranked by matching weak-group failure rate and include a human-readable reason.

#### Scenario: Exclude evaluated problem
- **WHEN** a failed DP problem and an untested DP problem exist
- **THEN** only the untested DP problem is recommended

### Requirement: Portable recommendation output

The system SHALL provide `harness recommend --history ... --output ...`, write a weakness report JSON, and write a sibling standard Problem JSON dataset. The dataset path SHALL be inferable from result metadata or explicitly supplied.

#### Scenario: Generate training dataset
- **WHEN** recommendation completes
- **THEN** the report contains weak groups, recommendation reasons, and a dataset path usable by a later `--dataset` evaluation
