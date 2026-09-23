# capability-map Specification

## ADDED Requirements

### Requirement: Heuristic capability dimensions

The system SHALL derive algorithm-design, code-implementation, debugging, optimization, and boundary-handling indicators from existing experiment metrics, preserving null values when denominators or usage are unavailable and documenting the heuristic nature.

#### Scenario: Missing formal tests
- **WHEN** a model has sample results but no independent hidden evaluations
- **THEN** the capability map does not fabricate a formal boundary score

### Requirement: Difficulty/tag coverage

The system SHALL expose success counts, denominators, and rates grouped by difficulty and algorithm tag for each model.

#### Scenario: Tag heatmap cell
- **WHEN** two combinations contain DP results with different outcomes
- **THEN** the heatmap cell reports the aggregated solved count, total count, and rate

### Requirement: HTML panel integration

The existing experiment HTML panel SHALL embed a capability radar and readable heatmap data without changing experiment execution.

#### Scenario: Offline panel
- **WHEN** Chart.js cannot load
- **THEN** the embedded capability table remains readable and the page explains the chart dependency
