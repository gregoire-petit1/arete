"""The coach's daily briefing: produced once a day, stored, read by the HUD.

- ``repository.py``: ``app.coach_briefings`` CRUD
- ``briefing.py``: the producer — one agent run, with the rule engine as its
  floor, called by the scheduler after a sync and by ``GET /tips/daily``
"""
