"""Garmin data pipeline module.

Handles FIT file parsing, session matching, and Garmin Connect sync.
"""

from arete.garmin.fit_parser import FITParser, ParsedActivity
from arete.garmin.matcher import SessionMatcher
from arete.garmin.models import ActualSession, PlannedSession, SessionMatch
from arete.garmin.repository import GarminRepository

__all__ = [
    "ActualSession",
    "FITParser",
    "GarminRepository",
    "ParsedActivity",
    "PlannedSession",
    "SessionMatch",
    "SessionMatcher",
]
