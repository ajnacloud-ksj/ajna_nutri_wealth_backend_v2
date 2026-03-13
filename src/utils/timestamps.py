"""
Centralized timestamp utilities.

IbexDB rejects timezone-aware ISO strings (e.g. +00:00 suffix).
All timestamps must use the format: YYYY-MM-DDTHH:MM:SS (no timezone offset).

Usage:
    from utils.timestamps import utc_now, utc_date, utc_time, utc_compact
"""

from datetime import datetime, timezone


def utc_now() -> str:
    """IbexDB-safe UTC timestamp: '2026-03-13T12:00:00'"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')


def utc_date() -> str:
    """UTC date only: '2026-03-13'"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def utc_time() -> str:
    """UTC time only: '12:00'"""
    return datetime.now(timezone.utc).strftime('%H:%M')


def utc_compact() -> str:
    """Compact UTC timestamp for IDs: '20260313120000'"""
    return datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')


def utc_epoch() -> float:
    """UTC epoch timestamp (float)."""
    return datetime.now(timezone.utc).timestamp()
