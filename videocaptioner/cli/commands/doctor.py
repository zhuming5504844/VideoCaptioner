"""doctor command -- diagnose local dependencies and configuration."""

import json
import shutil
import subprocess
import sys
from argparse import Namespace
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli.config import CONFIG_FILE, DEFAULTS, get
from videocaptioner.core.dubbing.presets import (
    get_dubbing_preset,
    normalize_dubbing_voice,
    validate_dubbing_voice,
)


@dataclass
class Check:
    name: str
    status: str
    message: str
    fix: str = ""


def run(args: Namespace, config: dict) -> int:
    checks = run_diagnostics(config, check_api=bool(getattr(args, "check_api", False)))
    if getattr(args, "json", False):
        print(
            json.dumps(
                {"checks": [asdict(c) for c in checks]}, ensure_ascii=False, indent=2
            )
        )
    else:
        _print_checks(checks)
    return (
        EXIT.DEPENDENCY_MISSING
        if any(c.status == "error" for c in checks)
        else EXIT.SUCCESS
    )


def run_diagnostics(
    config: dict, *, check_api: bool = False, check_download: bool = False
) -> list[Check]:
    """运行全部诊断检查，供 CLI 和 UI 诊断页共用。"""
    checks: list[Check] = []
    checks.append(_check_python())
    checks.append(
        _check_command(
            "ffmpeg",
            "Required for audio extraction, timing fit, muxing, and hard subtitles.",
        )
    )
    checks.append(_check_command("ffprobe", "Required for media duration checks."))
    checks.append(_check_ytdlp())
    checks.append(_check_config_file())
    checks.extend(_check_transcribe(config))
    checks.extend(_check_subtitle(config))
    checks.extend(_check_dubbing(config))
    if check_api or check_download:
        checks.extend(_check_download_sources())
    if check_api:
        checks.extend(_check_api(config))
    return checks


def _check_python() -> Check:
    version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    if (3, 10) <= sys.version_info[:2] < (3, 13):
        return Check("python", "ok", f"Python {version}")
    return Check(
        "python", "error", f"Python {version} is unsupported", "Use Python >=3.10,<3.13"
    )


def _check_command(name: str, purpose: str) -> Check:
    path = shutil.which(name)
    if not path:
        return Check(
            name,
            "error",
            f"{name} not found. {purpose}",
            f"Install {name} and make sure it is on PATH",
        )
    version = _command_version(name)
    return Check(name, "ok", f"{path}" + (f" ({version})" if version else ""))


def _check_ytdlp() -> Check:
    path = shutil.which("yt-dlp")
    if path:
        version = _command_version("yt-dlp")
        if version and _yt_dlp_version_is_old(version):
            return Check(
                "yt-dlp",
                "warn",
                f"{path} ({version}) may be old",
                "Update yt-dlp if online downloads fail",
            )
        return Check("yt-dlp", "ok", f"{path}" + (f" ({version})" if version else ""))
    try:
        import yt_dlp
        import yt_dlp.version

        version = getattr(yt_dlp.version, "__version__", "")
        return Check(
            "yt-dlp",
            "ok",
            "embedded yt_dlp module" + (f" ({version})" if version else ""),
        )
    except Exception:
        return Check(
            "yt-dlp",
            "error",
            "yt-dlp not found. Required by videocaptioner download.",
            "Install yt-dlp and make sure it is on PATH",
        )


def _yt_dlp_version_is_old(version: str) -> bool:
    try:
        year, month, _day = [int(part) for part in version.split(".")[:3]]
        release_date = date(year, month, _day)
    except Exception:
        return False
    # Stable yt-dlp versions are date-like.
    return (date.today() - release_date).days > 90


def _command_version(name: str) -> str:
    try:
        result = subprocess.run(
            [name, "-version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.splitlines()[0][:100]
    except Exception:
        pass
    try:
        result = subprocess.run(
            [name, "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.splitlines()[0][:100]
    except Exception:
        pass
    return ""


def _check_config_file() -> Check:
    if CONFIG_FILE.exists():
        return Check("config.file", "ok", str(CONFIG_FILE))
    return Check(
        "config.file",
        "warn",
        f"Config file does not exist: {CONFIG_FILE}",
        "Run 'videocaptioner config init' or set values with environment variables",
    )


def _check_transcribe(config: dict) -> list[Check]:
    asr = get(config, "transcribe.asr", "bijian")
    checks = [Check("transcribe.asr", "ok", f"default ASR: {asr}")]
    if asr == "whisper-api" and not get(config, "whisper_api.api_key", ""):
        checks.append(
            Check(
                "whisper_api.api_key",
                "error",
                "Whisper API key is missing",
                "Run 'videocaptioner config set whisper_api.api_key <key>'",
            )
        )
    if asr == "fun-asr" and not get(config, "fun_asr.api_key", ""):
        checks.append(Check("fun_asr.api_key", "error", "百炼 Fun-ASR API Key 未配置"))
    if asr == "deepgram" and not get(config, "deepgram.api_key", ""):
        checks.append(
            Check(
                "deepgram.api_key",
                "error",
                "Deepgram API Key 未配置。请设置 DEEPGRAM_API_KEY 环境变量或运行 'videocaptioner config set deepgram.api_key <key>'",
            )
        )
    if asr == "deepinfra" and not get(config, "deepinfra.api_key", ""):
        checks.append(
            Check(
                "deepinfra.api_key",
                "error",
                "DeepInfra API Key 未配置。请设置 DEEPINFRA_API_KEY 环境变量或运行 'videocaptioner config set deepinfra.api_key <key>'",
            )
        )
    if asr == "whisper-cpp" and not any(
        shutil.which(n) for n in ["whisper-cpp", "whisper", "whisper-cpp-main"]
    ):
        checks.append(
            Check(
                "whisper-cpp",
                "error",
                "whisper.cpp binary not found",
                "Install whisper.cpp or choose --asr bijian/whisper-api",
            )
        )
    return checks


def _check_subtitle(config: dict) -> list[Check]:
    checks: list[Check] = []
    optimize = bool(get(config, "subtitle.optimize", True))
    split = bool(get(config, "subtitle.split", True))
    translator = get(config, "translate.service", "bing")
    needs_llm = optimize or split or translator == "llm"
    checks.append(
        Check(
            "subtitle.processing",
            "ok",
            f"ai_polish={optimize}, split={split}, translator={translator}",
        )
    )
    if _is_ass_render_mode(get(config, "subtitle.render_mode", "ass")) and shutil.which(
        "ffmpeg"
    ):
        from videocaptioner.core.subtitle.ass_renderer import ffmpeg_supports_ass_filter

        if ffmpeg_supports_ass_filter():
            checks.append(
                Check("ffmpeg.ass_filter", "ok", "FFmpeg 支持 ASS 硬字幕渲染")
            )
        else:
            checks.append(
                Check(
                    "ffmpeg.ass_filter",
                    "error",
                    "当前 FFmpeg 不支持 ASS 硬字幕渲染",
                    "安装带 libass 的完整 FFmpeg，或在字幕样式里切换为圆角背景",
                )
            )
    if needs_llm and not get(config, "llm.api_key", ""):
        checks.append(
            Check(
                "llm.api_key",
                "warn",
                "LLM API key is missing; AI polish/split/LLM translation will fail",
                "Run 'videocaptioner config set llm.api_key <key>' or disable AI polish/split",
            )
        )
    if needs_llm and not get(config, "llm.model", ""):
        checks.append(
            Check(
                "llm.model",
                "error",
                "LLM model is missing",
                "Run 'videocaptioner config set llm.model <model>'",
            )
        )
    return checks


def _is_ass_render_mode(render_mode: str) -> bool:
    normalized = render_mode.strip().lower()
    return normalized in {"ass", "ass_style", "ass-style", "ass 样式", "ass样式"}


def _check_dubbing(config: dict) -> list[Check]:
    checks: list[Check] = []
    preset_name = get(config, "dubbing.preset", "")
    provider = get(config, "dubbing.provider", "edge")
    model = get(config, "dubbing.model", "")
    voice = get(config, "dubbing.voice", "")
    if preset_name:
        try:
            preset = get_dubbing_preset(preset_name)
            provider, model = preset.provider, preset.model
            if not voice or voice == DEFAULTS["dubbing"]["voice"]:
                voice = preset.voice
            checks.append(Check("dubbing.preset", "ok", f"{preset_name} ({provider})"))
        except ValueError as exc:
            checks.append(
                Check(
                    "dubbing.preset",
                    "error",
                    str(exc),
                    "Choose one of the presets shown in 'videocaptioner dub --help'",
                )
            )
    else:
        checks.append(
            Check(
                "dubbing.preset", "warn", "未配置配音预设", "请在配音页面选择一个声音"
            )
        )
    if provider != "edge" and not get(config, "dubbing.api_key", ""):
        checks.append(Check("dubbing.api_key", "warn", "配音 TTS API Key 未配置"))
    if provider not in {"siliconflow", "gemini", "edge"}:
        checks.append(
            Check(
                "dubbing.provider",
                "error",
                f"不支持的配音提供商: {provider}",
                "请使用 siliconflow、gemini 或 edge",
            )
        )
    normalized_voice = normalize_dubbing_voice(provider, model, voice)
    voice_error = validate_dubbing_voice(provider, normalized_voice)
    if voice_error:
        checks.append(
            Check("dubbing.voice", "error", voice_error, "请使用预设或提供商支持的声音")
        )
    else:
        checks.append(
            Check("dubbing.voice", "ok", normalized_voice or "(provider default)")
        )
    timing = get(config, "dubbing.timing", "balanced")
    audio_mode = get(config, "dubbing.audio_mode", "replace")
    if timing not in {"balanced", "strict", "natural", "none"}:
        checks.append(
            Check(
                "dubbing.timing",
                "error",
                f"无效的时间对齐模式: {timing}",
                "请使用 balanced、strict、natural 或 none",
            )
        )
    if audio_mode not in {"replace", "mix", "duck"}:
        checks.append(
            Check(
                "dubbing.audio_mode",
                "error",
                f"无效的原声处理模式: {audio_mode}",
                "请使用 replace、mix 或 duck",
            )
        )
    return checks


def _check_download_sources() -> list[Check]:
    """检查在线视频下载源（需要网络）。"""
    checks: list[Check] = []
    if not shutil.which("yt-dlp"):
        try:
            import yt_dlp  # noqa: F401
        except Exception:
            return []
    try:
        from videocaptioner.core.download.source_check import (
            DOWNLOAD_SOURCES,
            check_download_sources,
        )

        for result in check_download_sources():
            if result.success:
                checks.append(
                    Check(
                        f"api.download.{result.key}",
                        "ok",
                        f"{result.title}: 解析成功（{result.detail[:48]}）",
                    )
                )
            else:
                hint = ""
                for src in DOWNLOAD_SOURCES:
                    if src.key == result.key:
                        hint = src.fix_hint
                        break
                checks.append(
                    Check(
                        f"api.download.{result.key}",
                        "error",
                        f"{result.title}: {result.detail}",
                        hint,
                    )
                )
    except Exception as exc:
        checks.append(Check("api.download", "warn", f"下载源检查失败: {exc}"))
    return checks


def _check_api(config: dict) -> list[Check]:
    """检查实际 API 连通性（需要网络）。"""
    checks: list[Check] = []

    # 检查配音 API
    provider = get(config, "dubbing.provider", "edge")
    if provider != "edge":
        if get(config, "dubbing.api_key", ""):
            checks.append(
                Check("api.dubbing", "ok", f"配音提供商 {provider} 已配置 API Key")
            )
        else:
            checks.append(
                Check("api.dubbing", "warn", f"配音提供商 {provider} 需要 API Key")
            )

    # 检查 Whisper API
    asr = get(config, "transcribe.asr", "bijian")
    if asr == "whisper-api" and get(config, "whisper_api.api_key", ""):
        checks.append(Check("api.transcribe", "ok", "Whisper API 已配置"))
    elif asr == "fun-asr" and get(config, "fun_asr.api_key", ""):
        checks.append(Check("api.transcribe", "ok", "百炼 Fun-ASR 已配置"))

    return checks


def _print_checks(checks: list[Check]) -> None:
    for check in checks:
        prefix = {"ok": "OK", "warn": "WARN", "error": "ERROR"}.get(
            check.status, check.status.upper()
        )
        print(f"{prefix:5} {check.name}: {check.message}")
        if check.fix:
            print(f"      fix: {check.fix}")
    errors = sum(1 for c in checks if c.status == "error")
    warnings = sum(1 for c in checks if c.status == "warn")
    if errors:
        print(f"ERROR Doctor found {errors} error(s) and {warnings} warning(s)")
    elif warnings:
        print(f"WARN  Doctor found {warnings} warning(s)")
    else:
        print("OK    Doctor found no issues")
