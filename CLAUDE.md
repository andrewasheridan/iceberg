# CLAUDE.md

## Code style

- No banner or section-divider comments: no lines made only of `#` and a run of `-` or
  `=`, and no title comments wrapped in them. To group code, use a test class, a
  separate module or a docstring. `tests/unit/test_comment_style.py` and the
  `no-banner-comments` prek hook enforce this; see the Comments section of CONTRIBUTING.md.
- Write a comment only when it says something the code can't: a reason, a constraint
  or a non-obvious consequence. Don't label sections or restate what the code does.
- Readability matters: code is read far more often than it is written. When two ways
  work, pick the one that is easier to read. Follow the Zen of Python
  (`python -c "import this"`), above all: readability counts; explicit is better than
  implicit; simple is better than complex; flat is better than nested; sparse is
  better than dense; if the implementation is hard to explain, it's a bad idea.
- Whitespace is your friend. Use blank lines to split a function into its logical steps
  (setup, work, result) and to set off `if`/`for`/`with`/`try` blocks from the code
  around them. Flatten nesting with early returns, and prefer a plain loop or a named
  intermediate value to a clever one-liner. See the Readability section of
  CONTRIBUTING.md.
