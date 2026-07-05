"""Soniox ASR implementation — asynchronous REST API provider."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional

import requests
from requests import Session

from ..utils.logger import setup_logger
from .asr_data import ASRDataSeg
from .base import BaseASR

logger = setup_logger("soniox_asr")

SONIOX_BASE_URL = "https://api.soniox.com"
SONIOX_DEFAULT_MODEL = "stt-async-v5"

SONIOX_MODELS = {
    "stt-async-v5": "Async v5 (文件转录，推荐)",
}


def normalize_soniox_model(model: str | None) -> str:
    """Return the Soniox model id from a preset label or custom user input."""
    value = (model or SONIOX_DEFAULT_MODEL).strip()
    if not value:
        return SONIOX_DEFAULT_MODEL

    for model_id in SONIOX_MODELS:
        if value == model_id or value.startswith(f"{model_id} - "):
            return model_id

    return value


class SonioxASR(BaseASR):
    """Soniox Speech-to-Text Async API implementation.

    Uploads local audio bytes to Soniox Files API, creates an async transcription,
    polls until completion, downloads transcript tokens, and cleans up remote files.
    """

    def __init__(
        self,
        audio_input: Optional[str | bytes] = None,
        use_cache: bool = False,
        need_word_time_stamp: bool = False,
        api_key: str = "",
        model: str = SONIOX_DEFAULT_MODEL,
        language: str = "",
        enable_language_identification: bool = True,
        enable_speaker_diarization: bool = False,
        cleanup_remote_files: bool = True,
        poll_interval: float = 2.0,
    ):
        self.api_key = (api_key or os.getenv("SONIOX_API_KEY", "")).strip()
        self.model = normalize_soniox_model(model)
        self.language = language or ""
        self.enable_language_identification = enable_language_identification
        self.enable_speaker_diarization = enable_speaker_diarization
        self.cleanup_remote_files = cleanup_remote_files
        self.poll_interval = max(1.0, poll_interval)
        self.need_word_time_stamp = need_word_time_stamp
        super().__init__(audio_input, use_cache, need_word_time_stamp)

    def _get_key(self) -> str:
        return (
            f"{self.crc32_hex}:{self.model}:{self.language}:"
            f"{self.enable_language_identification}:"
            f"{self.enable_speaker_diarization}:{self.need_word_time_stamp}"
        )

    def _run(
        self, callback: Optional[Callable[[int, str], None]] = None, **kwargs: Any
    ) -> dict:
        if not self.api_key:
            raise ValueError(
                "Soniox API Key 未配置，请先在设置页或环境变量 SONIOX_API_KEY 中填写。"
            )

        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {self.api_key}"
        file_id: str | None = None
        transcription_id: str | None = None

        try:
            if callback:
                callback(20, "上传音频到 Soniox")
            file_id = self._upload_audio(session)

            if callback:
                callback(35, "创建 Soniox 转录任务")
            transcription_id = self._create_transcription(session, file_id)

            self._wait_until_completed(session, transcription_id, callback)

            if callback:
                callback(90, "下载 Soniox 转录结果")
            return self._get_transcript(session, transcription_id)
        finally:
            if self.cleanup_remote_files:
                if transcription_id:
                    self._delete_resource(session, f"/v1/transcriptions/{transcription_id}")
                if file_id:
                    self._delete_resource(session, f"/v1/files/{file_id}")

    def _upload_audio(self, session: Session) -> str:
        files = {"file": ("audio", self.file_binary or b"application/octet-stream")}
        response = session.post(f"{SONIOX_BASE_URL}/v1/files", files=files, timeout=600)
        response.raise_for_status()
        file_id = response.json().get("id")
        if not file_id:
            raise RuntimeError("Soniox 文件上传响应缺少 file id")
        return file_id

    def _create_transcription(self, session: Session, file_id: str) -> str:
        config: dict[str, Any] = {
            "model": self.model,
            "file_id": file_id,
            "enable_language_identification": self.enable_language_identification,
            "enable_speaker_diarization": self.enable_speaker_diarization,
        }
        if self.language:
            config["language_hints"] = [self.language]

        response = session.post(
            f"{SONIOX_BASE_URL}/v1/transcriptions", json=config, timeout=60
        )
        response.raise_for_status()
        transcription_id = response.json().get("id")
        if not transcription_id:
            raise RuntimeError("Soniox 创建转录响应缺少 transcription id")
        return transcription_id

    def _wait_until_completed(
        self,
        session: Session,
        transcription_id: str,
        callback: Optional[Callable[[int, str], None]],
    ) -> None:
        progress = 40
        while True:
            response = session.get(
                f"{SONIOX_BASE_URL}/v1/transcriptions/{transcription_id}", timeout=60
            )
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            if status == "completed":
                if callback:
                    callback(85, "Soniox 转录完成")
                return
            if status == "error":
                raise RuntimeError(f"Soniox 转录失败: {data.get('error_message', 'Unknown error')}")
            if callback:
                callback(progress, f"Soniox 转录中: {status or 'processing'}")
            progress = min(progress + 3, 84)
            time.sleep(self.poll_interval)

    def _get_transcript(self, session: Session, transcription_id: str) -> dict:
        response = session.get(
            f"{SONIOX_BASE_URL}/v1/transcriptions/{transcription_id}/transcript",
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def _delete_resource(self, session: Session, endpoint: str) -> None:
        try:
            session.delete(f"{SONIOX_BASE_URL}{endpoint}", timeout=30).raise_for_status()
        except requests.RequestException as e:
            logger.warning("Soniox 远程资源清理失败: %s", e)

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        tokens = resp_data.get("tokens", []) if isinstance(resp_data, dict) else []
        if not tokens:
            logger.warning("Soniox 未返回有效 tokens")
            return []

        if self.need_word_time_stamp:
            return self._tokens_to_word_segments(tokens)
        return self._tokens_to_text_segments(tokens)

    def _tokens_to_word_segments(self, tokens: list[dict]) -> list[ASRDataSeg]:
        segments: list[ASRDataSeg] = []
        for token in tokens:
            text = (token.get("text") or "").strip()
            if not text:
                continue
            start = self._token_ms(token, "start_ms", "start_time", 0)
            end = self._token_ms(token, "end_ms", "end_time", start)
            segments.append(ASRDataSeg(text=text, start_time=start, end_time=end))
        return segments

    def _tokens_to_text_segments(self, tokens: list[dict]) -> list[ASRDataSeg]:
        text_parts: list[str] = []
        start: int | None = None
        end = 0
        for token in tokens:
            text = token.get("text") or ""
            if not text:
                continue
            if start is None:
                start = self._token_ms(token, "start_ms", "start_time", 0)
            end = self._token_ms(token, "end_ms", "end_time", end)
            text_parts.append(text)
        text = "".join(text_parts).strip()
        return [ASRDataSeg(text=text, start_time=start or 0, end_time=end)] if text else []

    @staticmethod
    def _token_ms(token: dict, ms_key: str, seconds_key: str, default: int) -> int:
        if token.get(ms_key) is not None:
            return int(float(token[ms_key]))
        if token.get(seconds_key) is not None:
            return int(float(token[seconds_key]) * 1000)
        return default
