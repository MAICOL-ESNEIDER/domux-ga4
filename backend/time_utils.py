"""Colombian local time helpers for persisted application timestamps."""

from datetime import datetime, timedelta, timezone


COLOMBIA_TIMEZONE = timezone(timedelta(hours=-5))


def now_colombia():
    """Return Colombia's current wall-clock time as a naive datetime."""
    return datetime.now(COLOMBIA_TIMEZONE).replace(tzinfo=None)
