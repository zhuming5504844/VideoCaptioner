from __future__ import annotations

from typing import Any

from videocaptioner.core.asr.deepgram_asr import DeepgramASR


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"results": {"channels": []}}


def test_auto_language_enables_deepgram_detect_language(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _Response:
        captured["url"] = url
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr("requests.post", fake_post)

    asr = DeepgramASR(audio_input=b"audio", api_key="key", model="nova-3", language="")
    asr._submit_audio()

    assert captured["params"]["model"] == "nova-3-general"
    assert captured["params"]["detect_language"] == "true"
    assert "language" not in captured["params"]


def test_specified_language_uses_deepgram_language_parameter(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _Response:
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr("requests.post", fake_post)

    asr = DeepgramASR(audio_input=b"audio", api_key="key", model="nova-3-general", language="zh")
    asr._submit_audio()

    assert captured["params"]["language"] == "zh"
    assert "detect_language" not in captured["params"]
