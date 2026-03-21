---
name: test-writer
description: Writes pytest tests for existing implementation. Use after code-writer has implemented a feature to produce the test suite.
---

Write pytest tests for the implementation described or pointed to.

Rules:
- Tests live in `tests/`. Mirror the source structure: `src/sheridan/iceberg/foo.py` → `tests/test_foo.py`
- Use the `tmp_py` fixture from `conftest.py` for creating test files
- Aim for 90%+ branch coverage of the target module
- Test happy paths, edge cases, and error paths
- Use `pytest.raises` for expected exceptions
- Use `pytest.mark.parametrize` for data-driven cases
- Do not mock the `ast` module — use real source strings
- All test functions must have type annotations
- Do not add docstrings to test functions
