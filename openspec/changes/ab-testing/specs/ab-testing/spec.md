# ab-testing Specification

## ADDED Requirements

### Requirement: Two prompt variants

The system SHALL support exactly two prompt variants for one strategy, including IDs, descriptions, baseline selection, and prompt/system-prompt overrides.

#### Scenario: Treatment prompt override
- **WHEN** a treatment variant supplies a system prompt
- **THEN** only treatment requests receive that prompt and the report identifies both variants

### Requirement: Stratified assignment

The system SHALL assign problems using a fixed random seed within difficulty/tag strata, keeping arm counts balanced within one problem per stratum.

#### Scenario: Repeated seeded assignment
- **WHEN** the same dataset and seed are used twice
- **THEN** assignments are identical and each stratum has balanced arms

### Requirement: Statistical comparison report

The system SHALL report sample and formal success rates, treatment-minus-baseline difference with a 95% confidence interval, a small-sample-safe categorical test, Welch t-test output, Token/elapsed metrics, and difficulty/tag breakdowns with denominators.

#### Scenario: Small binary sample
- **WHEN** each arm has fewer than five expected observations
- **THEN** the report uses Fisher exact testing and retains p-value and confidence interval fields

### Requirement: CLI artifacts

The system SHALL provide `harness ab-test --config <file>` and produce JSON, CSV, and Markdown artifacts with a recommendation that avoids claiming causality from a single split.

#### Scenario: A/B run completes
- **WHEN** a valid configuration is executed
- **THEN** the output directory contains `ab_test.json`, `results.csv`, and `REPORT.md`
