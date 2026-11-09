"""Tests for scripts/limit_reset.py, which reads Claude Code usage-limit messages."""

import importlib.util
import io
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "limit_reset.py"
NEW_YORK = ZoneInfo("America/New_York")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("limit_reset", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


limit_reset = _load()


@pytest.mark.parametrize(
    "text",
    [
        "You've hit your 5-hour limit · resets 9:10pm (America/New_York)\n",
        "You've hit your limit · resets 3pm (Europe/London)",
        "some earlier output\n\nYou've hit your weekly limit · resets Nov 10, 9pm (America/New_York)\n\n",
        "Claude AI usage limit reached|1735689600",
    ],
)
def test_is_limit_message_true(text: str) -> None:
    assert limit_reset.is_limit_message(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "PR: https://github.com/o/r/pull/1",
        "You've hit your 5-hour limit · resets 9:10pm\nPR: https://github.com/o/r/pull/1",
    ],
)
def test_is_limit_message_false(text: str) -> None:
    assert not limit_reset.is_limit_message(text)


def test_reset_later_today() -> None:
    now = datetime(2026, 11, 8, 20, 15, tzinfo=NEW_YORK)
    text = "You've hit your 5-hour limit · resets 9:10pm (America/New_York)"
    assert limit_reset.reset_time(text, now) == datetime(2026, 11, 8, 21, 10, tzinfo=NEW_YORK)


def test_reset_time_already_passed_rolls_to_tomorrow() -> None:
    now = datetime(2026, 11, 8, 23, 0, tzinfo=NEW_YORK)
    text = "You've hit your 5-hour limit · resets 2am (America/New_York)"
    assert limit_reset.reset_time(text, now) == datetime(2026, 11, 9, 2, 0, tzinfo=NEW_YORK)


def test_reset_converts_between_zones() -> None:
    now = datetime(2026, 11, 9, 1, 0, tzinfo=UTC)  # 8pm in New York
    text = "You've hit your 5-hour limit · resets 9:10pm (America/New_York)"
    reset = limit_reset.reset_time(text, now)
    assert reset is not None
    assert (reset - now).total_seconds() == 70 * 60


def test_reset_12am_and_12pm() -> None:
    now = datetime(2026, 11, 8, 6, 0, tzinfo=NEW_YORK)
    noon = limit_reset.reset_time("hit your limit · resets 12pm (America/New_York)", now)
    midnight = limit_reset.reset_time("hit your limit · resets 12am (America/New_York)", now)
    assert noon == datetime(2026, 11, 8, 12, 0, tzinfo=NEW_YORK)
    assert midnight == datetime(2026, 11, 9, 0, 0, tzinfo=NEW_YORK)


def test_reset_with_date() -> None:
    now = datetime(2026, 11, 8, 20, 0, tzinfo=NEW_YORK)
    text = "You've hit your weekly limit · resets Nov 10, 9pm (America/New_York)"
    assert limit_reset.reset_time(text, now) == datetime(2026, 11, 10, 21, 0, tzinfo=NEW_YORK)


def test_reset_with_date_in_next_year() -> None:
    now = datetime(2026, 12, 30, 20, 0, tzinfo=NEW_YORK)
    text = "You've hit your weekly limit · resets Jan 2, 9am (America/New_York)"
    assert limit_reset.reset_time(text, now) == datetime(2027, 1, 2, 9, 0, tzinfo=NEW_YORK)


def test_reset_without_zone_uses_local_zone() -> None:
    now = datetime(2026, 11, 8, 20, 0, tzinfo=NEW_YORK)
    assert limit_reset.reset_time("hit your limit · resets 9pm", now) == datetime(2026, 11, 8, 21, 0, tzinfo=NEW_YORK)


def test_reset_with_unknown_zone_uses_local_zone() -> None:
    now = datetime(2026, 11, 8, 20, 0, tzinfo=NEW_YORK)
    reset = limit_reset.reset_time("hit your limit · resets 9pm (Not/AZone)", now)
    assert reset == datetime(2026, 11, 8, 21, 0, tzinfo=NEW_YORK)


def test_reset_epoch_format() -> None:
    now = datetime(2024, 12, 31, 0, 0, tzinfo=UTC)
    reset = limit_reset.reset_time("Claude AI usage limit reached|1735689600", now)
    assert reset == datetime(2025, 1, 1, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "text",
    [
        "You've hit your limit",
        "You've hit your weekly limit · resets Foo 10, 9pm (America/New_York)",
        "You've hit your weekly limit · resets Feb 31, 9pm (America/New_York)",
    ],
)
def test_reset_unreadable(text: str) -> None:
    now = datetime(2026, 11, 8, 20, 0, tzinfo=NEW_YORK)
    assert limit_reset.reset_time(text, now) is None


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("PR: https://github.com/o/r/pull/1\n", 2),
        ("You've hit your limit\n", 3),
        ("Claude AI usage limit reached|1000000000\n", 0),
    ],
)
def test_main_exit_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], text: str, status: int
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    assert limit_reset.main() == status
    out = capsys.readouterr().out
    assert out == ("0\n" if status == 0 else "")
