"""Read a Claude Code usage-limit message and print the seconds until the limit resets.

scripts/issue-loop.sh runs this when a headless session stops at a usage limit.
It reads the session's output on stdin. Exit status:

    0  the session stopped at a usage limit; prints the seconds until the reset
    2  the session did not stop at a usage limit
    3  the session stopped at a usage limit, but the reset time cannot be read

The loop treats every status other than 0 and 3 (a crash, for example) as "not
a usage limit", so a bug here falls back to stopping the loop.

Formats it reads:

    You've hit your 5-hour limit · resets 9:10pm (America/New_York)
    You've hit your weekly limit · resets Nov 10, 9pm (America/New_York)
    Claude AI usage limit reached|1735689600
"""

import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LIMIT_LINE = re.compile(r"(hit your .*limit|usage limit reached|limit reached)", re.IGNORECASE)
EPOCH = re.compile(r"usage limit reached\|(\d{9,})", re.IGNORECASE)
RESETS = re.compile(
    r"resets\s+(?:(?P<month>[A-Za-z]{3})[a-z]*\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)"
    r"(?:\s*\((?P<tz>[^)]+)\))?",
    re.IGNORECASE,
)
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def is_limit_message(text: str) -> bool:
    """Tell whether the output of a session ends at a usage limit.

    Only the last non-empty line counts, so a session that mentions limits in
    its work does not look like one that stopped at a limit.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    return bool(lines) and LIMIT_LINE.search(lines[-1]) is not None


def reset_time(text: str, now: datetime) -> datetime | None:
    """Find the reset time in a usage-limit message.

    Args:
        text: The output of the session.
        now: The current time. It must be timezone-aware.

    Returns:
        The reset time, or None when the message has no time that can be read.
    """
    if match := EPOCH.search(text):
        return datetime.fromtimestamp(int(match.group(1)), tz=now.tzinfo)
    match = RESETS.search(text)
    if match is None:
        return None
    try:
        tz = ZoneInfo(match["tz"].strip()) if match["tz"] else now.tzinfo
    except ZoneInfoNotFoundError, ValueError:
        tz = now.tzinfo
    local_now = now.astimezone(tz)
    hour = int(match["hour"]) % 12 + (12 if match["ampm"].lower() == "pm" else 0)
    minute = int(match["minute"] or 0)
    if match["month"]:
        month_name = match["month"].lower()[:3]
        if month_name not in MONTHS:
            return None
        try:
            candidate = local_now.replace(
                month=MONTHS.index(month_name) + 1,
                day=int(match["day"]),
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        except ValueError:
            return None
        if candidate < local_now - timedelta(days=1):
            candidate = candidate.replace(year=candidate.year + 1)
        return candidate
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def main() -> int:
    """Print the seconds until the usage limit in the output on stdin resets.

    Returns:
        The exit status described in the module docstring.
    """
    text = sys.stdin.read()
    if not is_limit_message(text):
        return 2
    now = datetime.now().astimezone()
    reset = reset_time(text, now)
    if reset is None:
        return 3
    print(max(0, int((reset - now).total_seconds())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
