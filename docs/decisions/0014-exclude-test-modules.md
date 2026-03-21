# 0014. Test Modules Are Always Excluded from `__all__` Checking

Date: 2026-03-21
Status: Accepted

## Context

Test files do not have or need `__all__`. Names imported into test modules are fixtures and assertions, not re-exports — enforcing `__all__` on them would produce IB001 noise on every test file, and AST inference would misinterpret imported names as public API.

## Decision

We decided that files matching `test_*.py`, `*_test.py`, or `conftest.py` are silently skipped by the walker, regardless of the path the user passes. The exclusion is implemented in `_is_test_file()` in `ast_walker.py` and applied in both `walk_path` and `load_modules`.

The skip patterns follow pytest's default discovery conventions, making the behaviour unsurprising to Python developers.

## Consequences

- No `--exclude` flag is needed for test directories; the exclusion is universal and automatic.
- Users cannot opt test files back in, but there is no legitimate reason to do so.
- The patterns mirror pytest's own discovery rules (`test_*.py`, `*_test.py`, `conftest.py`), so the set of skipped files is predictable without reading iceberg's documentation.
- Test files placed outside a `tests/` directory are still excluded correctly, since matching is by filename pattern rather than by directory name.
