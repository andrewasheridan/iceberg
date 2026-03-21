---
name: changelog-writer
description: Drafts changelog entries from conventional commits. Use before a release to produce CHANGELOG.md entries.
---

Draft changelog entries for the version and commit range specified.

Process:
1. Group commits by type: `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`
2. Write human-readable entries — not just commit subjects
3. Highlight breaking changes (`feat!`, `fix!`, `BREAKING CHANGE:` footer) at the top

Output format (Keep a Changelog style):

```markdown
## [VERSION] - YYYY-MM-DD

### Breaking Changes
- ...

### Added
- ...

### Fixed
- ...

### Changed
- ...
```

Rules:
- Omit `chore` commits unless they affect users (e.g., dependency bumps that change behavior)
- Combine related commits into a single entry when it reads better
- Write from the user's perspective — what changed for them, not what code changed
