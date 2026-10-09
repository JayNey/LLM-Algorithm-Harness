## Context

The codebase already uses `pathlib.Path` extensively (64 imports). This change addresses the remaining instances where URL path parsing incorrectly uses string splitting on forward slashes, which is semantically correct for URLs but creates confusion with filesystem path handling. See [proposal.md](proposal.md) for motivation.

## Goals / Non-Goals

**Goals:**
- Fix URL path parsing in `src/importers/leetcode.py` and `src/code_quality/readability_analyzer.py` where forward slash is used as a text delimiter, not a filesystem path separator
- Audit tests for Windows reserved filenames and case-sensitivity assumptions
- Document path handling conventions

**Non-Goals:**
- Migrating existing `pathlib.Path` usage (already standard in the codebase)
- Adding new filesystem path abstractions
- Changing URL construction or external API contracts

## Decisions

### Decision 1: Keep forward slash splitting for URL and text parsing

**Rationale**: The two instances found (`leetcode.py` line 142, `readability_analyzer.py` line 84) are correctly using forward slash as:
1. **URL path parsing**: `urlparse().path.split("/")` - forward slash is the URL path delimiter per RFC 3986, not a filesystem path
2. **Text parsing**: parsing pylint's "8.5/10" score output - forward slash is literal text

These are not filesystem path operations and should not use `os.sep` or `Path`. The code is semantically correct; we'll add clarifying comments to prevent future confusion.

**Alternative considered**: Replace with `os.sep` - rejected because these are URL/text operations, not filesystem paths, and would break on Windows where `os.sep` is backslash.

### Decision 2: Test audit focuses on fixture naming patterns

**Rationale**: Grep found no existing Windows reserved names in test files. The audit will focus on:
- Temporary file creation patterns that could generate reserved names
- Test fixtures that use arbitrary or user-derived names
- Any hardcoded test filenames

**Alternative considered**: Add runtime checks to reject reserved names - rejected as overkill since Python's `tempfile` module already avoids reserved names on Windows.

### Decision 3: Case sensitivity documented as known behavior

**Rationale**: Tests already use case-insensitive operations where appropriate (found `.lower()` usage in multiple test files). Path equality comparisons use `Path` objects, which handle case correctly per platform. Document that tests should use `Path` comparisons, not string equality.

**Alternative considered**: Force case-sensitive behavior via test mocks - rejected as it would hide real platform behavior and reduce test coverage.

## Risks / Trade-offs

- **Risk**: Tests might still have subtle case-sensitivity assumptions we didn't find → **Mitigation**: Windows CI will catch these during test runs
- **Risk**: Future contributors might add hardcoded forward slashes for filesystem paths → **Mitigation**: Add path handling guidelines to contributor docs
