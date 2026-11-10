import io

import requests

import ai
from test_app import app, login


WEBM = b"\x1a\x45\xdf\xa3" + b"audio"
MP4 = b"\x00\x00\x00\x18ftyp" + b"audio"
WAV = b"RIFF\x00\x00\x00\x00WAVE" + b"audio"


def post_audio(client, headers, audio=WEBM, language="ko"):
    return client.post("/api/transcribe", headers=headers, data={
        "language": language, "file": (io.BytesIO(audio), "recording"),
    })


def test_transcribe_requires_login_and_csrf(app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = app.test_client()
    with client.session_transaction() as session:
        session["csrf"] = "tok"
    assert post_audio(client, {"X-CSRF-Token": "tok"}).status_code == 401
    login(client, "employee")
    assert post_audio(client, {}).status_code == 400


def test_transcribe_unavailable_in_demo_mode(app, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = app.test_client()
    headers = login(client, "employee")
    assert post_audio(client, headers).status_code == 503
    assert b'id="voice"' in client.get("/").data


def test_transcription_validation(app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = app.test_client()
    headers = login(client, "employee")
    assert post_audio(client, headers, language="invalid").status_code == 400
    assert client.post("/api/transcribe", headers=headers, data={"language": "en"}).status_code == 400
    assert post_audio(client, headers, audio=b"").status_code == 400
    assert post_audio(client, headers, audio=b"not audio").status_code == 400
    assert post_audio(client, headers, audio=WEBM + b"x" * (10 * 1024 * 1024)).status_code == 413


def test_transcription_transport_and_formats(app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.example/v1/")
    monkeypatch.setenv("OPENAI_TRANSCRIBE_MODEL", "custom-model")
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"text": " 안녕하세요 "}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(ai.requests, "post", fake_post)
    client = app.test_client()
    headers = login(client, "employee")
    for audio, filename, mime in [(WEBM, "recording.webm", "audio/webm"),
                                  (MP4, "recording.mp4", "audio/mp4"),
                                  (WAV, "recording.wav", "audio/wav")]:
        response = post_audio(client, headers, audio)
        assert response.status_code == 200
        assert response.json == {"text": "안녕하세요"}
        url, args = calls[-1]
        assert url == "https://provider.example/v1/audio/transcriptions"
        assert args["headers"] == {"Authorization": "Bearer test-key"}
        assert args["data"] == {"model": "custom-model", "language": "ko"}
        assert args["files"]["file"] == (filename, audio, mime)
        assert args["timeout"] == 60


def test_transcription_errors_are_reported(app, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = app.test_client()
    headers = login(client, "employee")
    monkeypatch.setattr(ai, "transcribe", lambda *args: "")
    assert post_audio(client, headers).status_code == 422

    def fail(*args):
        raise requests.RequestException("provider error")

    monkeypatch.setattr(ai, "transcribe", fail)
    result = post_audio(client, headers)
    assert result.status_code == 502
    assert result.json["error"] == "Speech recognition service unavailable"
