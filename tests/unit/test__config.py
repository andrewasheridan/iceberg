"""Test sheridan.iceberg._config (the Config dataclass, load_config and load_config_file)."""

import dataclasses
import re
from pathlib import Path

import pytest

from sheridan.iceberg._config import Config, load_config, load_config_file
from sheridan.iceberg._exceptions import ConfigError

_DEFAULT_PATTERN_SRC = r"(^|/)tests?(/|$)|(^|/)test_[^/]*\.py$|_test\.py$"


def _write(path: Path, text: str) -> Path:
    """Write *text* to *path*. Make the parent directories if necessary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_config_defaults() -> None:
    cfg = Config()

    assert isinstance(cfg.test_module_pattern, re.Pattern)
    assert cfg.test_module_pattern.pattern == _DEFAULT_PATTERN_SRC
    assert cfg.max_workers == 1


def test_config_is_frozen() -> None:
    cfg = Config()
    assert dataclasses.is_dataclass(cfg)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.max_workers = 2  # type: ignore[misc]


def test_config_has_slots() -> None:
    assert hasattr(Config, "__slots__")
    assert len(Config.__slots__) > 0


def test_config_explicit_values() -> None:
    pattern = re.compile(r"test_.*\.py$")
    cfg = Config(
        test_module_pattern=pattern,
        max_workers=4,
    )

    assert cfg.test_module_pattern is pattern
    assert cfg.max_workers == 4


def test_load_config_no_file_returns_defaults(tmp_path: Path) -> None:
    # tmp_path/src does not exist. The walk resolves to tmp_path.
    cfg = load_config(tmp_path / "src")
    assert cfg.test_module_pattern.pattern == _DEFAULT_PATTERN_SRC
    assert cfg.max_workers == 1


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


def test_load_config_pyproject_toml_respected(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        "[tool.iceberg]\nmax_workers = 8\n",
    )
    cfg = load_config(tmp_path)
    assert cfg.max_workers == 8


def test_load_config_removed_include_subpackages_key_rejected(tmp_path: Path) -> None:
    """Version 4.0 removed ``include_subpackages_in_all``. It is now an unknown key."""
    _write(tmp_path / ".iceberg.toml", "include_subpackages_in_all = false\n")
    with pytest.raises(ConfigError, match="include_subpackages_in_all"):
        load_config(tmp_path)


def test_load_config_pyproject_without_iceberg_table_returns_defaults(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", '[tool.other]\nfoo = "bar"\n')
    cfg = load_config(tmp_path)
    assert cfg == Config()


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


def test_load_config_malformed_iceberg_toml_raises(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "max_workers = [not valid toml!!!\n")
    with pytest.raises(ConfigError, match="Cannot parse the TOML"):
        load_config(tmp_path)


def test_load_config_malformed_pyproject_toml_raises(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.iceberg\nbad syntax =\n")
    with pytest.raises(ConfigError, match="Cannot parse the TOML"):
        load_config(tmp_path)


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


def test_load_config_max_workers_non_integer_raises(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", 'max_workers = "four"\n')
    with pytest.raises(ConfigError, match="'max_workers' must be an integer"):
        load_config(tmp_path)


@pytest.mark.parametrize("value", ["true", "false"])
def test_load_config_max_workers_boolean_raises(tmp_path: Path, value: str) -> None:
    _write(tmp_path / ".iceberg.toml", f"max_workers = {value}\n")
    with pytest.raises(ConfigError, match="'max_workers' must be an integer, not 'bool'"):
        load_config(tmp_path)


def test_load_config_max_workers_float_raises(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "max_workers = 2.5\n")
    with pytest.raises(ConfigError, match="'max_workers' must be an integer"):
        load_config(tmp_path)


def test_load_config_found_in_parent(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "max_workers = 3\n")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    cfg = load_config(nested)

    assert cfg.max_workers == 3


def test_load_config_closer_ancestor_wins(tmp_path: Path) -> None:
    # The parent has max_workers = 1. The child has max_workers = 7.
    _write(tmp_path / ".iceberg.toml", "max_workers = 1\n")
    child = tmp_path / "subdir"
    child.mkdir()
    _write(child / ".iceberg.toml", "max_workers = 7\n")
    cfg = load_config(child)

    assert cfg.max_workers == 7


def test_load_config_nearer_pyproject_wins_over_distant_iceberg_toml(tmp_path: Path) -> None:
    # An .iceberg.toml far above (for example ~/.iceberg.toml) must not replace the project configuration.
    _write(tmp_path / ".iceberg.toml", "max_workers = 5\n")
    project = tmp_path / "project"
    _write(project / "pyproject.toml", "[tool.iceberg]\nmax_workers = 3\n")
    cfg = load_config(project / "src")

    assert cfg.max_workers == 3


def test_load_config_stops_at_pyproject_without_iceberg_table(tmp_path: Path) -> None:
    # The project root has no [tool.iceberg] table. The configuration of the parent project must not apply.
    _write(tmp_path / "pyproject.toml", "[tool.iceberg]\nmax_workers = 4\n")
    _write(tmp_path / ".iceberg.toml", "max_workers = 6\n")
    project = tmp_path / "vendor" / "project"
    _write(project / "pyproject.toml", '[tool.other]\nfoo = "bar"\n')
    cfg = load_config(project / "pkg")

    assert cfg == Config()


def test_load_config_nested_project_uses_its_own_config(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.iceberg]\nmax_workers = 4\n")
    inner = tmp_path / "packages" / "inner"
    _write(inner / "pyproject.toml", "[tool.iceberg]\nmax_workers = 2\n")

    assert load_config(inner / "src").max_workers == 2
    assert load_config(tmp_path / "packages").max_workers == 4


def test_load_config_iceberg_toml_below_project_root_wins(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[tool.iceberg]\nmax_workers = 4\n")
    _write(tmp_path / "src" / ".iceberg.toml", "max_workers = 9\n")
    assert load_config(tmp_path / "src" / "pkg").max_workers == 9


def test_load_config_iceberg_toml_above_project_root_ignored(tmp_path: Path) -> None:
    _write(tmp_path / ".iceberg.toml", "max_workers = 9\n")
    project = tmp_path / "project"
    _write(project / "pyproject.toml", "[project]\nname = 'x'\n")

    assert load_config(project).max_workers == 1


@pytest.mark.parametrize("value", [0, -1, -100])
def test_load_config_max_workers_non_positive_raises(tmp_path: Path, value: int) -> None:
    _write(tmp_path / ".iceberg.toml", f"max_workers = {value}\n")
    with pytest.raises(ConfigError, match="positive integer"):
        load_config(tmp_path)


def test_exclude_defaults_to_empty() -> None:
    """Config.exclude is empty by default."""
    assert Config().exclude == ()


def test_exclude_loaded_from_pyproject(tmp_path: Path) -> None:
    """load_config loads the exclude list in [tool.iceberg] as a tuple."""
    _write(tmp_path / "pyproject.toml", '[tool.iceberg]\nexclude = ["legacy", "**/*_pb2.py"]\n')

    assert load_config(tmp_path).exclude == ("legacy", "**/*_pb2.py")


@pytest.mark.parametrize("value", ['"legacy"', "[1, 2]", '["ok", 3]'])
def test_exclude_must_be_list_of_strings(tmp_path: Path, value: str) -> None:
    """A value that is not a list, or a list with items that are not strings, raises ConfigError."""
    _write(tmp_path / ".iceberg.toml", f"exclude = {value}\n")

    with pytest.raises(ConfigError, match="'exclude' must be a list of strings"):
        load_config(tmp_path)


def test_load_config_file_reads_top_level_keys(tmp_path: Path) -> None:
    """load_config_file reads a file with a name that is not pyproject.toml with its keys at the top level."""
    path = _write(tmp_path / "custom.toml", 'max_workers = 3\nexclude = ["a"]\n')

    config = load_config_file(path)

    assert config.max_workers == 3
    assert config.exclude == ("a",)


def test_load_config_file_does_not_search_upward(tmp_path: Path) -> None:
    """load_config_file ignores configuration files next to the named file or above it."""
    _write(tmp_path / ".iceberg.toml", "max_workers = 9\n")
    path = _write(tmp_path / "sub" / "custom.toml", "")

    assert load_config_file(path) == Config()


def test_load_config_file_reads_pyproject_table(tmp_path: Path) -> None:
    """load_config_file reads a file with the name pyproject.toml from its [tool.iceberg] table."""
    path = _write(tmp_path / "pyproject.toml", "[project]\nname = 'x'\n\n[tool.iceberg]\nmax_workers = 2\n")

    assert load_config_file(path).max_workers == 2


def test_load_config_file_pyproject_without_table_returns_defaults(tmp_path: Path) -> None:
    """A pyproject.toml without [tool.iceberg] gives the default values."""
    path = _write(tmp_path / "pyproject.toml", "[project]\nname = 'x'\n")

    assert load_config_file(path) == Config()


def test_load_config_file_missing_raises(tmp_path: Path) -> None:
    """A path that is not a file raises ConfigError."""
    with pytest.raises(ConfigError, match="configuration file does not exist"):
        load_config_file(tmp_path / "missing.toml")


def test_load_config_file_directory_raises(tmp_path: Path) -> None:
    """load_config_file does not accept a directory as a configuration file."""
    with pytest.raises(ConfigError, match="configuration file does not exist"):
        load_config_file(tmp_path)


def test_load_config_file_validates_keys(tmp_path: Path) -> None:
    """load_config_file does not accept unknown keys in the named file."""
    path = _write(tmp_path / "custom.toml", "bogus = 1\n")

    with pytest.raises(ConfigError, match="Unknown configuration key"):
        load_config_file(path)
