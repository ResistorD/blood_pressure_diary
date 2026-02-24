"""Time utilities for consistent datetime handling across the application."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Union


def now_utc() -> datetime:
    """Get current UTC time with timezone info.
    
    Returns:
        datetime: Current UTC time with timezone information
        
    Example:
        >>> dt = now_utc()
        >>> dt.tzinfo is not None
        True
    """
    return datetime.now(timezone.utc)


def parse_iso(ts: Union[str, datetime]) -> datetime:
    """Parse ISO timestamp, handling various formats.
    
    Handles both 'Z' suffix and '+00:00' timezone formats.
    If datetime is passed, returns it unchanged.
    
    Args:
        ts: ISO timestamp string or datetime object
        
    Returns:
        datetime: Parsed datetime with timezone
        
    Example:
        >>> dt = parse_iso("2024-01-01T12:00:00Z")
        >>> dt.year
        2024
    """
    if isinstance(ts, datetime):
        return ts
    # Handle both 'Z' and '+00:00' suffixes
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def to_iso(dt: datetime) -> str:
    """Convert datetime to ISO string with seconds precision.
    
    Args:
        dt: datetime to convert
        
    Returns:
        str: ISO format string with seconds precision
        
    Example:
        >>> from datetime import timezone
        >>> dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        >>> to_iso(dt)
        '2024-01-01T12:00:00+00:00'
    """
    return dt.isoformat(timespec="seconds")


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime has UTC timezone.
    
    If datetime is naive (no timezone), assumes UTC.
    If datetime has different timezone, converts to UTC.
    
    Args:
        dt: datetime to ensure is UTC
        
    Returns:
        datetime: datetime in UTC timezone
    """
    if dt.tzinfo is None:
        # Naive datetime, assume UTC
        return dt.replace(tzinfo=timezone.utc)
    # Convert to UTC if different timezone
    return dt.astimezone(timezone.utc)
