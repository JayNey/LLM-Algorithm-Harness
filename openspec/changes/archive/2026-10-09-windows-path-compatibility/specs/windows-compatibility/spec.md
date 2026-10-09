## ADDED Requirements

### Requirement: URL path parsing SHALL NOT conflate URL separators with filesystem path separators

When parsing URLs to extract slug or path components, the system SHALL use URL parsing that treats forward slashes as URL path delimiters, not as filesystem path separators. URL path parsing SHALL remain independent of the host platform's filesystem conventions.

#### Scenario: Parse LeetCode URL on Windows
- **WHEN** a LeetCode URL like "https://leetcode.com/problems/two-sum/" is parsed on Windows
- **THEN** the slug "two-sum" is extracted correctly without filesystem path handling errors

#### Scenario: Parse pylint score with forward slash on Windows
- **WHEN** pylint output containing "Your code has been rated at 8.5/10" is parsed on Windows
- **THEN** the score 8.5 is extracted correctly by splitting on forward slash as a text delimiter

### Requirement: Test fixtures SHALL avoid Windows reserved filenames

Test data and fixtures SHALL NOT use Windows reserved device names as filenames. Reserved names include: `CON`, `PRN`, `AUX`, `NUL`, `COM1` through `COM9`, and `LPT1` through `LPT9` (case-insensitive, with or without extensions).

#### Scenario: Test creates temporary files with arbitrary names
- **WHEN** tests create files with names that could be user-provided or generated
- **THEN** no file is named with a Windows reserved device name, preventing "Access is denied" or "The system cannot find the file specified" errors on Windows

### Requirement: Filesystem case sensitivity SHALL NOT be assumed

Code and tests SHALL NOT assume case-sensitive filesystem behavior. File lookups, comparisons, and test assertions SHALL work correctly on both case-sensitive (Linux, macOS with APFS case-sensitive) and case-insensitive (Windows, default macOS) filesystems.

#### Scenario: File existence check on case-insensitive filesystem
- **WHEN** code checks for existence of a file with different casing than what was written
- **THEN** behavior is consistent and documented, without assuming case-sensitivity

#### Scenario: Test assertions about file paths
- **WHEN** tests verify file paths are created or referenced correctly
- **THEN** assertions work on both case-sensitive and case-insensitive filesystems
