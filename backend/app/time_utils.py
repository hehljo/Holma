"""UTC timestamp helpers preserving the project's naive SQLite representation."""

from datetime import datetime, timezone


def utc_now_naive():
    """Return naive UTC for existing SQLAlchemy ``DateTime`` columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso_z():
    """Return an explicit RFC 3339 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

