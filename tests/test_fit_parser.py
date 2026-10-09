"""FIT session record: cadence lands in the units the other sources use."""

from __future__ import annotations

from types import SimpleNamespace

from arete.garmin.fit_parser import FITParser, ParsedActivity


def _session(**fields):
    return SimpleNamespace(
        fields=[SimpleNamespace(name=k, value=v) for k, v in fields.items()]
    )


def test_running_cadence_is_converted_to_steps():
    # fitparse names the field avg_running_cadence on runs, in strides/min
    activity = ParsedActivity()
    FITParser()._parse_session_record(
        _session(
            sport="running",
            avg_running_cadence=86,
            avg_fractional_cadence=0.5,
            max_running_cadence=95,
        ),
        activity,
    )
    assert activity.avg_cadence == 173
    assert activity.max_cadence == 190


def test_cycling_cadence_stays_in_rpm():
    activity = ParsedActivity()
    FITParser()._parse_session_record(
        _session(sport="cycling", avg_cadence=88, max_cadence=110), activity
    )
    assert (activity.avg_cadence, activity.max_cadence) == (88, 110)
