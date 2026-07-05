"""Tests for DeepInfra ASR integration helpers."""

from videocaptioner.core.asr.deepinfra_asr import (
    DEEPINFRA_DEFAULT_MODEL,
    DEEPINFRA_MAX_SEGMENT_DURATION_MS,
    DeepInfraASR,
    normalize_deepinfra_model,
)
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum


def test_normalize_deepinfra_model_from_label() -> None:
    assert (
        normalize_deepinfra_model(
            "openai/whisper-timestamped-large-v3 - Whisper Timestamped Large V3（时间轴优先）"
        )
        == "openai/whisper-timestamped-large-v3"
    )


def test_normalize_deepinfra_model_default() -> None:
    assert normalize_deepinfra_model("") == DEEPINFRA_DEFAULT_MODEL


def test_make_segments_from_response() -> None:
    asr = DeepInfraASR(audio_input=b"\x00", use_cache=False)
    segments = asr._make_segments(
        {
            "text": "Hello world.",
            "segments": [
                {"start": 0.25, "end": 1.5, "text": "Hello"},
                {"start": 1.5, "end": 2.75, "text": "world."},
            ],
        }
    )

    assert len(segments) == 2
    assert segments[0].text == "Hello"
    assert segments[0].start_time == 250
    assert segments[0].end_time == 1500
    assert segments[1].text == "world."


def test_make_segments_falls_back_to_text() -> None:
    asr = DeepInfraASR(audio_input=b"\x00", use_cache=False)
    asr.audio_duration = 1
    segments = asr._make_segments({"text": "Only transcript."})

    assert len(segments) == 1
    assert segments[0].text == "Only transcript."
    assert segments[0].start_time == 0
    assert segments[0].end_time == 1000


def test_make_segments_splits_text_only_response_by_audio_duration() -> None:
    asr = DeepInfraASR(audio_input=b"\x00", use_cache=False, language="en")
    asr.audio_duration = 29.5

    segments = asr._make_segments(
        {
            "text": (
                "That just describes something that's really good. Amazing. "
                "And earlier we learned the word marvelous. "
                "Rocky Steps can you tell us? "
                "Well today we get to see Zach and Bella."
            )
        }
    )

    assert len(segments) > 1
    assert segments[0].start_time == 0
    assert segments[-1].end_time == 29500
    assert all(
        segment.end_time - segment.start_time <= DEEPINFRA_MAX_SEGMENT_DURATION_MS
        for segment in segments
    )
    assert " ".join(segment.text for segment in segments) == (
        "That just describes something that's really good. Amazing. "
        "And earlier we learned the word marvelous. "
        "Rocky Steps can you tell us? "
        "Well today we get to see Zach and Bella."
    )


def test_transcribe_config_includes_deepinfra_fields() -> None:
    config = TranscribeConfig(
        transcribe_model=TranscribeModelEnum.DEEPINFRA,
        deepinfra_api_key="di-test-key",
        deepinfra_model="openai/whisper-large-v3",
        deepinfra_task="translate",
        deepinfra_temperature=0.2,
    )

    output = config.print_config()

    assert config.transcribe_model == TranscribeModelEnum.DEEPINFRA
    assert "DeepInfra" in output
    assert "openai/whisper-large-v3" in output
    assert "translate" in output


def test_submit_audio_adds_language_lock_prompt(monkeypatch) -> None:
    captured = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"text": "Hello"}

    def fake_post(url, headers, data, files, timeout):
        captured["data"] = data
        return DummyResponse()

    monkeypatch.setattr("videocaptioner.core.asr.deepinfra_asr.requests.post", fake_post)

    asr = DeepInfraASR(audio_input=b"\x00", api_key="test-key", language="en")
    result = asr._submit_audio()

    assert result == {"text": "Hello"}
    data = dict(captured["data"])
    granularities = [
        value for key, value in captured["data"] if key == "timestamp_granularities[]"
    ]
    assert data["response_format"] == "verbose_json"
    assert granularities == ["word", "segment"]
    assert data["language"] == "en"
    assert "English only" in data["prompt"]
    assert "Do not translate" in data["prompt"]


def test_make_segments_prefers_words_over_segment_timestamps() -> None:
    asr = DeepInfraASR(audio_input=b"\x00", use_cache=False, language="en")
    segments = asr._make_segments(
        {
            "segments": [
                {
                    "start": 99,
                    "end": 120,
                    "text": "Bad segment timing.",
                    "words": [
                        {"start": 0.25, "end": 0.7, "word": "Good"},
                        {"start": 0.7, "end": 1.2, "word": "word"},
                        {"start": 1.2, "end": 1.5, "word": "timing."},
                    ],
                }
            ]
        }
    )

    assert len(segments) == 1
    assert segments[0].text == "Good word timing."
    assert segments[0].start_time == 250
    assert segments[0].end_time == 1500


def test_make_segments_removes_cjk_leakage_for_english() -> None:
    asr = DeepInfraASR(audio_input=b"\x00", use_cache=False, language="en")
    segments = asr._make_segments(
        {
            "segments": [
                {
                    "start": 0,
                    "end": 1,
                    "text": "I bought one of the artist's newest works. 我买了那位艺术家最新的作品之一。",
                }
            ]
        }
    )

    assert len(segments) == 1
    assert segments[0].text == "I bought one of the artist's newest works."


def test_make_segments_splits_long_deepinfra_segments_to_readable_duration() -> None:
    asr = DeepInfraASR(audio_input=b"\x00", use_cache=False, language="en")
    segments = asr._make_segments(
        {
            "segments": [
                {
                    "start": 0,
                    "end": 29.5,
                    "text": (
                        "That just describes something that's really good. Amazing. "
                        "And earlier we learned the word marvelous. "
                        "Rocky Steps can you tell us? "
                        "Well today we get to see Zach and Bella."
                    ),
                }
            ]
        }
    )

    assert len(segments) > 1
    assert segments[0].start_time == 0
    assert segments[-1].end_time == 29500
    assert all(
        segment.end_time - segment.start_time <= DEEPINFRA_MAX_SEGMENT_DURATION_MS
        for segment in segments
    )
    assert " ".join(segment.text for segment in segments) == (
        "That just describes something that's really good. Amazing. "
        "And earlier we learned the word marvelous. "
        "Rocky Steps can you tell us? "
        "Well today we get to see Zach and Bella."
    )
