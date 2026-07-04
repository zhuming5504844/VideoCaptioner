"""Deepgram ASR implementation — synchronous HTTP API provider."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

import requests

from ..utils.logger import setup_logger
from .asr_data import ASRDataSeg
from .base import BaseASR

logger = setup_logger("deepgram_asr")

DEEPGRAM_BASE_URL = "https://api.deepgram.com"
DEEPGRAM_DEFAULT_MODEL = "nova-2"

DEEPGRAM_MODELS = {
    "nova-2": "Nova-2 (通用，推荐)",
    "nova-3": "Nova-3 (最新，增强)",
    "base-general": "Base (基础)",
    "whisper": "Whisper (OpenAI)",
}


def normalize_deepgram_model(model: str | None) -> str:
    """Return the Deepgram model id from a preset label or custom user input."""
    value = (model or DEEPGRAM_DEFAULT_MODEL).strip()
    if not value:
        return DEEPGRAM_DEFAULT_MODEL

    for model_id in DEEPGRAM_MODELS:
        if value == model_id or value.startswith(f"{model_id} - "):
            return model_id

    return value

# Languages that rely on Nova-2's built-in 30+ language support
# Passed as BCP-47 tags in the language query param.
# Deepgram supports auto-detection when language is omitted.
DEEPGRAM_LANGUAGE_MAP: dict[str, str] = {
    "en": "en",
    "zh": "zh-CN",
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


class DeepgramASR(BaseASR):
    """Deepgram speech-to-text API implementation.

    Sends raw audio bytes directly to the Deepgram REST API.
    Supports word-level timestamps, punctuation, smart formatting,
    speaker diarization, and more.
    """

    def __init__(
        self,
        audio_input: Optional[str | bytes] = None,
        use_cache: bool = False,
        need_word_time_stamp: bool = False,
        api_key: str = "",
        model: str = DEEPGRAM_DEFAULT_MODEL,
        language: str = "",
        punctuate: bool = True,
        smart_format: bool = True,
        diarize: bool = False,
        paragraphs: bool = False,
        utterances: bool = False,
        filler_words: bool = False,
        numerals: bool = False,
    ):
        self.api_key = (api_key or os.getenv("DEEPGRAM_API_KEY", "")).strip()
        self.model = normalize_deepgram_model(model)
        self.language = language or ""
        self.punctuate = punctuate
        self.smart_format = smart_format
        self.diarize = diarize
        self.paragraphs = paragraphs
        self.utterances = utterances
        self.filler_words = filler_words
        self.numerals = numerals
        self.need_word_time_stamp = need_word_time_stamp
        super().__init__(audio_input, use_cache, need_word_time_stamp)

    def _get_key(self) -> str:
        return (
            f"{self.crc32_hex}:{self.model}:{self.language}:"
            f"{self.punctuate}:{self.smart_format}:{self.diarize}:"
            f"{self.need_word_time_stamp}"
        )

    def _run(
        self, callback: Optional[Callable[[int, str], None]] = None, **kwargs: Any
    ) -> dict:
        if not self.api_key:
            raise ValueError(
                "Deepgram API Key 未配置，请先在设置页或环境变量 DEEPGRAM_API_KEY 中填写。"
            )

        if callback:
            callback(30, "发送转录请求")

        response = self._submit_audio()

        if callback:
            callback(90, "解析转录结果")

        return response

    def _submit_audio(self) -> dict:
        """Send audio bytes to Deepgram and return parsed JSON response."""
        url = f"{DEEPGRAM_BASE_URL}/v1/listen"

        # Build query parameters
        params: dict[str, str] = {
            "model": self.model,
            "punctuate": "true" if self.punctuate else "false",
            "smart_format": "true" if self.smart_format else "false",
        }
        if self.language:
            bcp47 = DEEPGRAM_LANGUAGE_MAP.get(self.language, self.language)
            params["language"] = bcp47
        if self.need_word_time_stamp:
            params["diarize"] = "true" if self.diarize else "false"
            params["paragraphs"] = "true" if self.paragraphs else "false"
            params["utterances"] = "true" if self.utterances else "false"
            params["filler_words"] = "true" if self.filler_words else "false"
            params["numerals"] = "true" if self.numerals else "false"

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "audio/wav",
        }

        logger.debug(
            "Deepgram request: model=%s, language=%s, params=%s",
            self.model, self.language or "auto", params,
        )

        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                data=self.file_binary or b"",
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
            logger.error("Deepgram API 请求失败: %s", detail or str(e))
            raise RuntimeError(
                f"Deepgram 转录请求失败: {detail or str(e)}"
            ) from e

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        """Convert Deepgram response to segment list.

        Response structure:
            results.channels[i].alternatives[j].words[k].{word, start, end, confidence}
        """
        segments: list[ASRDataSeg] = []

        try:
            channels = (
                resp_data.get("results", {})
                .get("channels", [])
            )
        except AttributeError:
            logger.error("Deepgram 响应格式异常: %s", str(resp_data)[:300])
            return segments

        for channel in channels:
            alternatives = channel.get("alternatives", [])
            for alt in alternatives:
                # Use word-level timestamps if available
                words = alt.get("words", [])
                if words and self.need_word_time_stamp:
                    for word in words:
                        text = (word.get("word") or "").strip()
                        if not text:
                            continue
                        start = int(float(word.get("start", 0)) * 1000)
                        end = int(float(word.get("end", 0)) * 1000)
                        segments.append(
                            ASRDataSeg(text=text, start_time=start, end_time=end)
                        )
                else:
                    # Fall back to paragraph/sentence boundaries
                    paragraphs_data = alt.get("paragraphs", {})
                    para_list = paragraphs_data.get("paragraphs", [])
                    if para_list:
                        for para in para_list:
                            sentences = para.get("sentences", [])
                            for sent in sentences:
                                text = (sent.get("text") or "").strip()
                                if not text:
                                    continue
                                start = int(float(sent.get("start", 0)) * 1000)
                                end = int(float(sent.get("end", 0)) * 1000)
                                segments.append(
                                    ASRDataSeg(
                                        text=text,
                                        start_time=start,
                                        end_time=end,
                                    )
                                )
                    else:
                        # No paragraphs — use full transcript as one segment
                        transcript = (alt.get("transcript") or "").strip()
                        if transcript:
                            segments.append(
                                ASRDataSeg(
                                    text=transcript,
                                    start_time=0,
                                    end_time=0,
                                )
                            )

        if not segments:
            logger.warning("Deepgram 未返回有效字幕段")

        return segments
