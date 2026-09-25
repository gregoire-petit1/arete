"""Reading what the athlete wrote or said: workout grammar, parser, transcription.

No text generation lives here any more — the coaching agent owns that, in
``arete.agent``. What is left is deterministic (the Lark grammar and the
free-text parser) plus the speech-to-text call behind dictated sessions.
"""
