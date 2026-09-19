# model-client Specification

## ADDED Requirements

### Requirement: Effective strategy parameters

The client SHALL apply strategy-level temperature, max_tokens, system_prompt, and custom_params to the actual provider request, falling back to global LLMConfig values when no override is provided. The resulting non-secret parameter snapshot SHALL be retained in each response trace.

#### Scenario: Strategy override reaches provider
- **WHEN** a strategy sets temperature 0.1, max_tokens 321, and a system prompt
- **THEN** the provider request contains those exact values and the trace contains the redacted effective snapshot

### Requirement: Unified compatible providers

The `openai`, `siliconflow`, and `local` providers SHALL use the OpenAI-compatible protocol. `local` SHALL require an explicit base_url; SiliconFlow SHALL retain its preset base URL and key lookup.

#### Scenario: Local endpoint declaration
- **WHEN** provider is local with a base_url
- **THEN** the client initializes the OpenAI-compatible SDK against that URL

### Requirement: Bounded API retry

The client SHALL perform at most the configured total attempts for 429, 5xx, timeout, and connection errors, with a testable backoff and elapsed-time limit. 401/403 and other parameter/client errors SHALL fail immediately, and SDK-level implicit retries SHALL be disabled.

#### Scenario: Rate limit and authentication
- **WHEN** a request returns 429 repeatedly
- **THEN** it stops at the configured attempt limit; a 401 makes exactly one request

### Requirement: Response and usage compatibility

The client SHALL preserve a problem trace when content is empty, truncated, represented by multiple text blocks, or accompanied by optional reasoning. Missing usage SHALL be marked unknown and SHALL NOT be reported as a zero-cost call.

#### Scenario: Multiple blocks and missing usage
- **WHEN** a provider returns multiple text blocks without usage
- **THEN** text blocks are concatenated, reasoning remains separate, and pricing metadata marks usage unknown with no total cost
