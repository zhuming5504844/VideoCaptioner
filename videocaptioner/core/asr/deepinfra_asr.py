"""DeepInfra ASR implementation — synchronous HTTP API provider."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

import requests

from ..utils.logger import setup_logger
from .asr_data import ASRDataSeg
from .base import BaseASR

logger = setup_logger("deepinfra_asr")

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/inference"
DEEPINFRA_DEFAULT_MODEL = "openai/whisper-large-v3-turbo"

DEEPINFRA_MODELS = {
    "mistralai/Voxtral-Mini-3B-2507": "Voxtral Mini 3B 2507",
    "mistralai/Voxtral-Small-24B-2507": "Voxtral Small 24B 2507",
    "nvidia/Nemotron-3.5-ASR-Streaming-Multilingual-0.6b": "Nemotron 3.5 ASR Streaming Multilingual 0.6B",
    "openai/whisper-large-v3": "Whisper Large V3",
    "openai/whisper-large-v3-turbo": "Whisper Large V3 Turbo（推荐）",
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
                text = (segment.get("text") or "").strip()
                if not text:
                    continue
                start = int(float(segment.get("start", 0) or 0) * 1000)
                end = int(float(segment.get("end", 0) or 0) * 1000)
                segments.append(ASRDataSeg(text=text, start_time=start, end_time=end))

        if not segments:
            text = (resp_data.get("text") or "").strip()
            if text:
                segments.append(ASRDataSeg(text=text, start_time=0, end_time=0))

        if not segments:
            logger.warning("DeepInfra 未返回有效字幕段")

        return segments
