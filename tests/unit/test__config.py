"""Tests for sheridan.iceberg._config (Config dataclass and load_config)."""

import dataclasses
import re
from pathlib import Path

import pytest

from sheridan.iceberg._config import Config, load_config
from sheridan.iceberg._exceptions import ConfigError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_PATTERN_SRC = r"(^|/)tests?(/|$)|(^|/)test_[^/]*\.py$|_test\.py$"


def _write(path: Path, text: str) -> Path:
    """Write *text* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Config dataclass - unit tests (no filesystem)
# ---------------------------------------------------------------------------


def test_config_defaults() -> None:
    cfg = Config()
    assert isinstance(cfg.test_module_pattern, re.Pattern)
    assert cfg.test_module_pattern.pattern == _DEFAULT_PATTERN_SRC
    assert cfg.include_subpackages_in_all is True
    assert cfg.max_workers is None


def test_config_is_frozen() -> None:
    cfg = Config()
    assert dataclasses.is_dataclass(cfg)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.include_subpackages_in_all = False  # type: ignore[misc]


def test_config_has_slots() -> None:
    assert hasattr(Config, "__slots__")
    assert len(Config.__slots__) > 0


def test_config_explicit_values() -> None:
    pattern = re.compile(r"test_.*\.py$")
    cfg = Config(
        test_module_pattern=pattern,
        include_subpackages_in_all=False,
        max_workers=4,
    )
    assert cfg.test_module_pattern is pattern
    assert cfg.include_subpackages_in_all is False
    assert cfg.max_workers == 4


# ---------------------------------------------------------------------------
# 1. Defaults returned when no config file exists in any ancestor
# ---------------------------------------------------------------------------


def test_load_config_no_file_returns_defaults(tmp_path: Path) -> None:
    # tmp_path/src does not exist; the walk resolves to tmp_path itself
    cfg = load_config(tmp_path / "src")
    assert cfg.test_module_pattern.pattern == _DEFAULT_PATTERN_SRC
    assert cfg.include_subpackages_in_all is True
    assert cfg.max_workers is None


# ---------------------------------------------------------------------------
# 2. .iceberg.toml wins when both files are present in the same directory
# ---------------------------------------------------------------------------


def test_load_config_iceberg_toml_wins_over_pyproject(tmp_path: Path) -> None:
    _write(
        tmp_path / ".iceberg.toml",
        "max_workers = 2\n",
    )
    _write(
        tmp_path / "pyproject.toml",
        "[tool.iceberg]\nmax_workers = 99\n",
    )
    cfg = load_config(tmp_path)
    assert cfg.max_workers == 2


# ---------------------------------------------------------------------------
# 3. pyproject.toml [tool.iceberg] is respected when .iceberg.toml is absent
# ---------------------------------------------------------------------------


def test_load_config_pyproject_toml_respected(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        "[tool.iceberg]\ninclude_subpackages_in_all = false\nmax_workers = 8\n",
    )
    cfg = load_config(tmp_path)
    assert cfg.include_subpackages_in_all is False
    assert cfg.max_workers == 8


def test_load_config_pyproject_without_iceberg_table_returns_defaults(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", '[tool.other]\nfoo = "bar"\n')
    cfg = load_config(tmp_path)
    assert cfg == Config()


# ---------------------------------------------------------------------------
# 4. test_module_pattern from config compiles to a re.Pattern
# ---------------------------------------------------------------------------


def test_load_config_custom_pattern_compiles(tmp_path: Path) -> None:
    _write(
        tmp_path / ".iceberg.toml",
        'test_module_pattern = "^tests/"\n',
    )
    cfg = load_config(tmp_path)
    assert isinstance(cfg.test_module_pattern, re.Pattern)
    assert cfg.test_module_pattern.pattern == "^tests/"
    assert cfg.test_module_pattern.match("tests/foo.py") is not None
    assert cfg.test_module_pattern.match("src/foo.py") is None


# ---------------------------------------------------------------------------
# 5. Invalid regex raises ConfigError
# ---------------------------------------------------------------------------


def test_load_config_invalid_regex_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / ".iceberg.toml",
        'test_module_pattern = "[invalid"\n',
    )
    with pytest.raises(ConfigError, match="not a valid regular expression"):
        load_config(tmp_path)


def test_load_config_invalid_regex_in_pyproject_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.iceberg]\ntest_module_pattern = "(*bad"\n',
    )
    with pytest.raises(ConfigError):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# 6. Malformed TOML raises ConfigError
# ---------------------------------------------------------------------------


def test_load_config_malformed_iceberg_toml_raises(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "max_workers = [not valid toml!!!\n")
    with pytest.raises(ConfigError, match="Failed to parse TOML"):
        load_config(tmp_path)


def test_load_config_malformed_pyproject_toml_raises(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.iceberg\nbad syntax =\n")
    with pytest.raises(ConfigError, match="Failed to parse TOML"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# 7. Unknown key raises ConfigError
# ---------------------------------------------------------------------------


def test_load_config_unknown_key_in_iceberg_toml_raises(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "unknown_option = true\n")
    with pytest.raises(ConfigError, match="Unknown configuration key"):
        load_config(tmp_path)


def test_load_config_unknown_key_in_pyproject_raises(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        "[tool.iceberg]\nnot_a_real_key = 42\n",
    )
    with pytest.raises(ConfigError, match="Unknown configuration key"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# 8. max_workers with a non-integer value raises ConfigError
# ---------------------------------------------------------------------------


def test_load_config_max_workers_non_integer_raises(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", 'max_workers = "four"\n')
    with pytest.raises(ConfigError, match="'max_workers' must be an integer"):
        load_config(tmp_path)


def test_load_config_max_workers_float_raises(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "max_workers = 2.5\n")
    with pytest.raises(ConfigError, match="'max_workers' must be an integer"):
        load_config(tmp_path)


# ---------------------------------------------------------------------------
# Ancestor walk - config found in a parent directory
# ---------------------------------------------------------------------------


def test_load_config_found_in_parent(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "max_workers = 3\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    cfg = load_config(nested)
    assert cfg.max_workers == 3


def test_load_config_closer_ancestor_wins(tmp_path: Path) -> None:
    # Parent has max_workers = 1; child has max_workers = 7
    _write(tmp_path / ".iceberg.toml", "max_workers = 1\n")
    child = tmp_path / "subdir"
    child.mkdir()
    _write(child / ".iceberg.toml", "max_workers = 7\n")
    cfg = load_config(child)
    assert cfg.max_workers == 7


# ---------------------------------------------------------------------------
# max_workers positive integer constraint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -1, -100])
def test_load_config_max_workers_non_positive_raises(tmp_path: Path, value: int) -> None:
    _write(tmp_path / ".iceberg.toml", f"max_workers = {value}\n")
    with pytest.raises(ConfigError, match="positive integer"):
        load_config(tmp_path)
