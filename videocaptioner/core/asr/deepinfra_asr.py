"""DeepInfra ASR implementation — synchronous HTTP API provider."""

from __future__ import annotations

import math
import os
import re
from typing import Any, Callable, Optional

import requests

from ..utils.logger import setup_logger
from ..utils.text_utils import is_mainly_cjk
from .asr_data import ASRDataSeg
from .base import BaseASR

logger = setup_logger("deepinfra_asr")

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/inference"
DEEPINFRA_DEFAULT_MODEL = "openai/whisper-large-v3-turbo"
DEEPINFRA_MAX_SEGMENT_DURATION_MS = 7000
DEEPINFRA_MAX_SEGMENT_CHARS_CJK = 42
DEEPINFRA_MAX_SEGMENT_CHARS_LATIN = 84

DEEPINFRA_MODELS = {
    "mistralai/Voxtral-Mini-3B-2507": "Voxtral Mini 3B 2507",
    "mistralai/Voxtral-Small-24B-2507": "Voxtral Small 24B 2507",
    "nvidia/Nemotron-3.5-ASR-Streaming-Multilingual-0.6b": "Nemotron 3.5 ASR Streaming Multilingual 0.6B",
    "openai/whisper-large-v3": "Whisper Large V3",
    "openai/whisper-large-v3-turbo": "Whisper Large V3 Turbo（推荐）",
}

DEEPINFRA_LANGUAGE_NAMES: dict[str, str] = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ru": "Russian",
    "it": "Italian",
    "nl": "Dutch",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "tl": "Tagalog",
    "hi": "Hindi",
    "ar": "Arabic",
}

DEEPINFRA_LANGUAGE_MAP: dict[str, str] = {
    "zh": "zh",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "pt": "pt",
    "ru": "ru",
    "it": "it",
    "nl": "nl",
    "vi": "vi",
    "th": "th",
    "id": "id",
    "ms": "ms",
    "tl": "tl",
    "hi": "hi",
    "ar": "ar",
}


def _split_text_into_subtitle_chunks(text: str) -> list[str]:
    """Split long DeepInfra text into subtitle-sized chunks."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    max_chars = (
        DEEPINFRA_MAX_SEGMENT_CHARS_CJK
        if is_mainly_cjk(text)
        else DEEPINFRA_MAX_SEGMENT_CHARS_LATIN
    )
    if len(text) <= max_chars:
        return [text]

    parts = [
        part.strip()
        for part in re.split(r"(?<=[。！？!?；;：:，,\.])\s*", text)
        if part.strip()
    ]
    if not parts:
        parts = [text]

    chunks: list[str] = []
    current = ""
    for part in parts:
        separator = "" if not current or is_mainly_cjk(current + part) else " "
        candidate = f"{current}{separator}{part}" if current else part
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = part
        else:
            current = candidate

        while len(current) > max_chars:
            split_at = current.rfind(" ", 0, max_chars + 1)
            if split_at <= 0:
                split_at = max_chars
            chunks.append(current[:split_at].strip())
            current = current[split_at:].strip()

    if current:
        chunks.append(current)

    return chunks


def _split_segment_to_subtitle_duration(seg: ASRDataSeg) -> list[ASRDataSeg]:
    """Keep one DeepInfra segment within a generally readable subtitle duration."""
    duration = max(seg.end_time - seg.start_time, 0)
    chunks = _split_text_into_subtitle_chunks(seg.text)
    if not chunks:
        return []
    if len(chunks) == 1 and duration <= DEEPINFRA_MAX_SEGMENT_DURATION_MS:
        return [seg]

    target_chunk_count = max(
        len(chunks), math.ceil(duration / DEEPINFRA_MAX_SEGMENT_DURATION_MS)
    )
    if len(chunks) < target_chunk_count:
        words = re.findall(r"\S+", seg.text)
        units = words if len(words) >= target_chunk_count else list(seg.text)
        separator = " " if units is words else ""
        chunks = []
        units_per_chunk = math.ceil(len(units) / target_chunk_count)
        for index in range(0, len(units), units_per_chunk):
            chunk = separator.join(units[index : index + units_per_chunk]).strip()
            if chunk:
                chunks.append(chunk)

    current_time = seg.start_time
    result: list[ASRDataSeg] = []
    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            end_time = seg.end_time
        else:
            chunk_duration = int(duration / max(len(chunks), 1))
            end_time = min(seg.end_time, current_time + max(chunk_duration, 1))
        result.append(ASRDataSeg(text=chunk, start_time=current_time, end_time=end_time))
        current_time = end_time

    return result


def _language_lock_prompt(language: str) -> str:
    """Return a Whisper prompt that keeps output in the requested language."""
    language = (language or "").strip().lower()
    if not language:
        return ""

    language_name = DEEPINFRA_LANGUAGE_NAMES.get(language, language)
    return (
        f"Transcribe the audio in {language_name} only. "
        f"Do not translate to any other language. "
        f"If speech is unclear, keep the transcript in {language_name}."
    )


def _strip_unwanted_script_for_language(text: str, language: str) -> str:
    """Remove obvious cross-language leakage for strict language-specific output."""
    if (language or "").strip().lower() != "en" or not text:
        return text

    # Whisper can occasionally leak CJK translations into English transcriptions.
    # For an explicit English transcription request, remove those characters while
    # preserving English words, numbers, punctuation and spacing.
    text = re.sub(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+[，。！？；：、]*", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def normalize_deepinfra_model(model: str | None) -> str:
    """Return the DeepInfra model id from a preset label or custom user input."""
    value = (model or DEEPINFRA_DEFAULT_MODEL).strip()
    if not value:
        return DEEPINFRA_DEFAULT_MODEL

    for model_id in DEEPINFRA_MODELS:
        if value == model_id or value.startswith(f"{model_id} - "):
            return model_id

    return value


class DeepInfraASR(BaseASR):
    """DeepInfra speech-to-text API implementation.

    Sends audio as multipart/form-data to DeepInfra's speech-recognition inference
    endpoint and converts the returned sentence-level timestamps into ASR segments.
    """

    def __init__(
        self,
        audio_input: Optional[str | bytes] = None,
        use_cache: bool = False,
        need_word_time_stamp: bool = False,
        api_key: str = "",
        model: str = DEEPINFRA_DEFAULT_MODEL,
        language: str = "",
        task: str = "transcribe",
        temperature: float = 0,
    ):
        self.api_key = (api_key or os.getenv("DEEPINFRA_API_KEY", "")).strip()
        self.model = normalize_deepinfra_model(model)
        self.language = language or ""
        self.task = task or "transcribe"
        self.temperature = temperature
        self.need_word_time_stamp = need_word_time_stamp
        super().__init__(audio_input, use_cache, need_word_time_stamp)

    def _get_key(self) -> str:
        return (
            f"{self.crc32_hex}:{self.model}:{self.language}:"
            f"{self.task}:{self.temperature}:{self.need_word_time_stamp}"
        )

    def _run(
        self, callback: Optional[Callable[[int, str], None]] = None, **kwargs: Any
    ) -> dict:
        if not self.api_key:
            raise ValueError(
                "DeepInfra API Key 未配置，请先在设置页或环境变量 DEEPINFRA_API_KEY 中填写。"
            )

        if callback:
            callback(30, "发送 DeepInfra 转录请求")

        response = self._submit_audio()

        if callback:
            callback(90, "解析 DeepInfra 转录结果")

        return response

    def _submit_audio(self) -> dict:
        """Send audio bytes to DeepInfra and return parsed JSON response."""
        url = f"{DEEPINFRA_BASE_URL}/{self.model}"
        data: dict[str, str] = {"task": self.task}
        if self.language:
            data["language"] = DEEPINFRA_LANGUAGE_MAP.get(self.language, self.language)
            prompt = _language_lock_prompt(data["language"])
            if prompt:
                data["prompt"] = prompt
        if self.temperature is not None:
            data["temperature"] = str(self.temperature)

        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"audio": ("audio.wav", self.file_binary or b"", "audio/wav")}

        logger.debug(
            "DeepInfra request: model=%s, language=%s, task=%s",
            self.model,
            self.language or "auto",
            self.task,
        )

        try:
            response = requests.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=600,
            )
            response.raise_for_status()
            result: dict = response.json()
            return result
        except requests.RequestException as e:
            detail = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    detail = e.response.text[:500]
                except Exception:
                    detail = str(e.response.status_code)
            logger.error("DeepInfra API 请求失败: %s", detail or str(e))
            raise RuntimeError(f"DeepInfra 转录请求失败: {detail or str(e)}") from e

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        """Convert DeepInfra response to segment list."""
        segments: list[ASRDataSeg] = []

        if not isinstance(resp_data, dict):
            logger.error("DeepInfra 响应格式异常: %s", str(resp_data)[:300])
            return segments

        raw_segments = resp_data.get("segments") or []
        if isinstance(raw_segments, list):
            for segment in raw_segments:
                if not isinstance(segment, dict):
                    continue
                text = _strip_unwanted_script_for_language(
                    (segment.get("text") or "").strip(), self.language
                )
                if not text:
                    continue
                start = int(float(segment.get("start", 0) or 0) * 1000)
                end = int(float(segment.get("end", 0) or 0) * 1000)
                segments.extend(
                    _split_segment_to_subtitle_duration(
                        ASRDataSeg(text=text, start_time=start, end_time=end)
                    )
                )

        if not segments:
            text = _strip_unwanted_script_for_language(
                (resp_data.get("text") or "").strip(), self.language
            )
            if text:
                segments.append(ASRDataSeg(text=text, start_time=0, end_time=0))

        if not segments:
            logger.warning("DeepInfra 未返回有效字幕段")

        return segments
