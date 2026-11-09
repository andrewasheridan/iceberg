# CLAUDE.md

## Code style

- No banner or section-divider comments: no lines made only of `#` and a run of `-` or
  `=`, and no title comments wrapped in them. To group code, use a test class, a
  separate module or a docstring. `tests/unit/test_comment_style.py` and the
  `no-banner-comments` pre-commit hook enforce this; see the Comments section of CONTRIBUTING.md.
- Write a comment only when it says something the code can't: a reason, a constraint
  or a non-obvious consequence. Don't label sections or restate what the code does.
