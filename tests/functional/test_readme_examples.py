"""Golden tests for the examples in the main README and every ``cases/*/README.md``.

Each ``console`` block holds one ``$ iceberg ...`` command followed by its
expected output. The command is run from the project root through the CLI's
``main`` and its stdout must match the documented output exactly, so the docs
and the code cannot drift apart without a failed test.
"""

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import pytest

from sheridan.iceberg._cli import main

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_READMES = [_PROJECT_ROOT / "README.md", *sorted((_PROJECT_ROOT / "cases").glob("*/README.md"))]
_CONSOLE_BLOCK = re.compile(r"^```console\n(.*?)^```$", re.MULTILINE | re.DOTALL)
_PROMPT = "$ "


@dataclass(frozen=True)
class _Example:
    readme: Path
    argv: list[str]
    expected: str

    @property
    def id(self) -> str:
        return f"{self.readme.relative_to(_PROJECT_ROOT)}::{shlex.join(['iceberg', *self.argv])}"


def _parse_block(readme: Path, block: str) -> _Example:
    command, _, expected = block.partition("\n")
    assert command.startswith(_PROMPT), f"{readme}: console block must start with '{_PROMPT}iceberg ...'"
    program, *argv = shlex.split(command.removeprefix(_PROMPT))
    assert program == "iceberg", f"{readme}: console block must run iceberg, got {program!r}"
    assert _PROMPT not in expected, f"{readme}: console block must hold exactly one command"
    return _Example(readme=readme, argv=argv, expected=expected)


def _collect() -> list[_Example]:
    return [
        _parse_block(readme, match.group(1))
        for readme in _READMES
        for match in _CONSOLE_BLOCK.finditer(readme.read_text(encoding="utf-8"))
    ]


_EXAMPLES = _collect()


def test_every_readme_has_an_example() -> None:
    """Each README must contribute at least one example, so a renamed block fence cannot skip a case silently."""
    documented = {example.readme for example in _EXAMPLES}
    missing = [str(readme.relative_to(_PROJECT_ROOT)) for readme in _READMES if readme not in documented]
    assert not missing, f"READMEs without a console example: {missing}"


@pytest.mark.parametrize("example", _EXAMPLES, ids=lambda example: example.id)
def test_readme_example_matches_cli_output(
    example: _Example, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(_PROJECT_ROOT)

    exit_code = main(example.argv)

    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    assert captured.out == example.expected
