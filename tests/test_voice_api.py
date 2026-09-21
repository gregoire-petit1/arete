"""POST /strength/sessions/transcribe: dictation in, notation out."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from arete.api.strength import router
from arete.llm.transcription import TranscriptionError, TranscriptionResult

DICTATION = "squat 3 séries de 5 à 100 kilos puis tractions 4 séries de 8"


@pytest.fixture
def client(router_client):
    return router_client(router)


def audio_file(name: str = "dictation.webm", content: bytes = b"audio-bytes"):
    return {"file": (name, content, "audio/webm")}


def transcribed(text: str, cost: float | None = None):
    return TranscriptionResult(
        text=text, model="whisper", cost_usd=cost, audio_bytes=11
    )


class TestTranscribeEndpoint:
    def test_returns_transcript_and_notation(self, client):
        with patch(
            "arete.llm.transcription.transcribe", return_value=transcribed(DICTATION)
        ):
            body = client.post(
                "/strength/sessions/transcribe", files=audio_file()
            ).json()
        assert body["transcript"] == DICTATION
        assert body["notation"] == "squat 3x5 @100\ntractions 4x8"
        assert body["exercises"] == 2
        assert body["unparsed"] == []

    def test_reports_the_cost(self, client):
        with patch(
            "arete.llm.transcription.transcribe",
            return_value=transcribed(DICTATION, cost=0.00012),
        ):
            body = client.post(
                "/strength/sessions/transcribe", files=audio_file()
            ).json()
        assert body["cost_usd"] == 0.00012

    def test_what_the_grammar_cannot_read_comes_back_verbatim(self, client):
        spoken = "squat 3 séries de 5. il faisait chaud dans la salle"
        with (
            patch(
                "arete.llm.transcription.transcribe", return_value=transcribed(spoken)
            ),
            patch("arete.api.strength._record_dictation_misses") as record,
        ):
            body = client.post(
                "/strength/sessions/transcribe", files=audio_file()
            ).json()
        assert body["exercises"] == 1
        assert body["unparsed"] == ["il faisait chaud dans la salle"]
        record.assert_called_once()

    def test_nothing_is_saved(self, client):
        # the athlete proof-reads, then sends the notation through /sessions/parse
        with patch(
            "arete.llm.transcription.transcribe", return_value=transcribed(DICTATION)
        ):
            body = client.post(
                "/strength/sessions/transcribe", files=audio_file()
            ).json()
        assert "session_id" not in body

    def test_safari_audio_is_accepted(self, client):
        with patch(
            "arete.llm.transcription.transcribe", return_value=transcribed(DICTATION)
        ) as transcribe:
            client.post(
                "/strength/sessions/transcribe", files=audio_file("dictation.m4a")
            )
        assert transcribe.call_args.kwargs["filename"] == "dictation.m4a"

    def test_empty_upload_is_refused(self, client):
        resp = client.post(
            "/strength/sessions/transcribe", files=audio_file(content=b"")
        )
        assert resp.status_code == 400

    def test_oversized_upload_is_refused(self, client, monkeypatch):
        monkeypatch.setenv("STT_MAX_AUDIO_MB", "0")
        resp = client.post("/strength/sessions/transcribe", files=audio_file())
        assert resp.status_code == 413
        assert "volumineux" in resp.json()["detail"]


class TestFailures:
    @pytest.mark.parametrize(
        ("reason", "status"),
        [
            ("unconfigured", 503),
            ("unsupported_format", 400),
            ("timeout", 504),
            ("upstream", 502),
            ("empty", 422),
        ],
    )
    def test_each_reason_maps_to_its_status(self, client, reason, status):
        with patch(
            "arete.llm.transcription.transcribe",
            side_effect=TranscriptionError(reason, f"échec {reason}"),
        ):
            resp = client.post("/strength/sessions/transcribe", files=audio_file())
        assert resp.status_code == status
        assert resp.json()["detail"] == f"échec {reason}"

    def test_a_dictation_with_no_exercise_still_answers(self, client):
        with patch(
            "arete.llm.transcription.transcribe",
            return_value=transcribed("je me sens bien aujourd'hui"),
        ):
            resp = client.post("/strength/sessions/transcribe", files=audio_file())
        assert resp.status_code == 200
        body = resp.json()
        assert body["exercises"] == 0
        assert body["notation"] == ""
        assert body["unparsed"] == ["je me sens bien aujourd'hui"]
