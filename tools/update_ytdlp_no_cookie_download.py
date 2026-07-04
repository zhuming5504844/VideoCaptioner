#!/usr/bin/env python3
"""手动更新 yt-dlp，并以 No Cookie 模式下载 YouTube 视频。

用法：
    python tools/update_ytdlp_no_cookie_download.py
    python tools/update_ytdlp_no_cookie_download.py "https://www.youtube.com/watch?v=4JrAauj_X9w"

脚本会先尝试更新当前 Python 环境中的 yt-dlp，再调用 yt-dlp 的 Python API 下载。
No Cookie 模式会显式忽略 cookies.txt / 浏览器 cookies，适合下载公开 YouTube 视频。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_URL = "https://www.youtube.com/watch?v=4JrAauj_X9w"
DEFAULT_CLIENTS = "mweb,ios,android,web_safari"
YOUTUBE_NO_COOKIE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _run_command(command: list[str]) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, check=True)


def update_yt_dlp(skip_update: bool = False) -> None:
    """更新当前环境中的 yt-dlp；无 pip 时回退到 uv pip。"""
    if skip_update:
        print("已跳过 yt-dlp 更新。")
        return

    pip_command = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
    if shutil.which("uv"):
        uv_command = ["uv", "pip", "install", "--upgrade", "yt-dlp", "--python", sys.executable]
    else:
        uv_command = []

    try:
        _run_command(pip_command)
    except subprocess.CalledProcessError:
        if not uv_command:
            raise
        print("当前 Python 环境没有可用 pip，改用 uv pip 更新 yt-dlp。")
        _run_command(uv_command)


def build_ydl_options(output_dir: Path, clients: str, disable_proxy: bool) -> dict[str, Any]:
    """构建 No Cookie 下载参数，供脚本和测试复用。"""
    player_clients = [client.strip() for client in clients.split(",") if client.strip()]
    options: dict[str, Any] = {
        "paths": {"home": str(output_dir)},
        "outtmpl": {"default": "%(title).200s.%(ext)s"},
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "ignore_no_formats_error": False,
        "nocheckcertificate": True,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "http_headers": {"User-Agent": YOUTUBE_NO_COOKIE_UA},
        "extractor_args": {"youtube": {"player_client": player_clients}},
        # 关键：显式 No Cookie，不读取 cookies.txt，也不读取浏览器登录态。
        "cookiefile": None,
        "cookiesfrombrowser": None,
    }
    if disable_proxy:
        options["proxy"] = ""
    return options


def download_no_cookie(url: str, output_dir: Path, clients: str, disable_proxy: bool) -> None:
    import yt_dlp
    import yt_dlp.version

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"yt-dlp version: {yt_dlp.version.__version__}")
    print(f"No Cookie 下载 URL: {url}")
    print(f"输出目录: {output_dir}")
    options = build_ydl_options(output_dir, clients, disable_proxy)
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="更新 yt-dlp 并以 No Cookie 模式下载 YouTube 视频")
    parser.add_argument("url", nargs="?", default=None, help=f"YouTube URL，默认：{DEFAULT_URL}")
    parser.add_argument("-o", "--output", default="downloads", help="下载输出目录，默认：downloads")
    parser.add_argument("--skip-update", action="store_true", help="跳过 yt-dlp 更新，只执行下载")
    parser.add_argument(
        "--clients",
        default=DEFAULT_CLIENTS,
        help=f"逗号分隔的 YouTube player_client 列表，默认：{DEFAULT_CLIENTS}",
    )
    parser.add_argument(
        "--disable-proxy",
        action="store_true",
        help="禁用环境变量代理；代理异常时可使用，例如 Tunnel connection failed: 403 Forbidden",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    url = args.url or input(f"请输入 YouTube URL（直接回车使用默认 {DEFAULT_URL}）：").strip() or DEFAULT_URL
    output_dir = Path(args.output).expanduser().resolve()

    if args.disable_proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(key, None)

    try:
        update_yt_dlp(args.skip_update)
        download_no_cookie(url, output_dir, args.clients, args.disable_proxy)
    except subprocess.CalledProcessError as exc:
        print(f"命令执行失败，退出码：{exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    except Exception as exc:
        message = str(exc)
        print(f"下载失败：{message}", file=sys.stderr)
        if "Sign in to confirm" in message or "not a bot" in message:
            print(
                "该视频被 YouTube 风控要求登录验证；No Cookie 模式无法绕过 YouTube 的登录/机器人校验。"
                "请确认视频为公开可匿名播放，或稍后换网络/IP 后重试。",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
