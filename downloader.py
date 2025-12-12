"""Video downloading utilities using yt-dlp."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

SUPPORTED_DOMAINS = re.compile(
    r"https?://(?:(?:www|m)\.)?(youtube\.com|youtu\.be|instagram\.com|instagr\.am)/",
    re.IGNORECASE,
)

QUALITY_MAP = {
    "360p":  "best[ext=mp4][height<=360][acodec!=none][vcodec!=none]/bestvideo[height<=360]+bestaudio/best",
    "480p":  "best[ext=mp4][height<=480][acodec!=none][vcodec!=none]/bestvideo[height<=480]+bestaudio/best",
    "720p":  "best[ext=mp4][height<=720][acodec!=none][vcodec!=none]/bestvideo[height<=720]+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best",  # 1080p ko‘pincha alohida video+audio bo‘ladi
    "best":  "bestvideo+bestaudio/best",
    "mp3":   "bestaudio/best",
}



@dataclass
class DownloadResult:
    """Metadata about the downloaded video."""

    file_path: Path
    title: str
    ext: str
    size: int


class DownloadError(Exception):
    """Base class for download errors."""


class UnsupportedURLError(DownloadError):
    """Raised when URL domain is not supported."""


class FileTooLargeError(DownloadError):
    """Raised when expected file size exceeds allowed maximum."""


class DownloadFailedError(DownloadError):
    """Raised when yt-dlp fails to download the video."""


ProgressCallback = Callable[[dict], None]


def _estimate_size(info: dict) -> Optional[int]:
    """Estimate the file size from yt-dlp info structure."""

    # Try common fields first
    for key in ("filesize", "filesize_approx"):
        if key in info and info[key]:
            return int(info[key])

    # For adaptive streams, check formats
    formats = info.get("formats") or []
    sizes = [f.get("filesize") or f.get("filesize_approx") for f in formats if f.get("filesize") or f.get("filesize_approx")]
    if sizes:
        return int(max(sizes))
    return None


def _build_opts(
    url: str,
    quality_key: str,
    tmp_dir: Path,
    max_file_bytes: int,
    progress_cb: Optional[ProgressCallback],
    user_agent: Optional[str],
    cookies_path: Optional[Path],
) -> dict:
    outtmpl = str(tmp_dir / "video.%(ext)s")

    def _hook(d: dict) -> None:
        if progress_cb:
            progress_cb(d)
        # Proactively abort if we know size exceeds limit.
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total and total > max_file_bytes:
            raise FileTooLargeError(f"File is too large: {total} bytes exceeds limit {max_file_bytes}")

    format_selector = QUALITY_MAP.get(quality_key, QUALITY_MAP["best"])
    is_audio = quality_key == "mp3"

    opts = {
        "format": format_selector,
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "ignoreerrors": False,
        "progress_hooks": [_hook],
    }

    if is_audio:
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        opts["merge_output_format"] = "mp4"

    if user_agent:
        opts["http_headers"] = {"User-Agent": user_agent}
    if cookies_path:
        opts["cookiefile"] = str(cookies_path)
    opts["ffmpeg_location"] = str(Path.home() / "ffmpeg")
        # YouTube JS challenge solver + runtime (deno)
    opts["remote_components"] = "ejs:github"
    opts["js_runtimes"] = {
        "deno": {"path": str(Path.home() / ".deno" / "bin" / "deno")}
    }
    # SABR/web client muammosini kamaytirish
    opts.setdefault("extractor_args", {})
    opts["extractor_args"].setdefault("youtube", {})
    opts["extractor_args"]["youtube"]["player_client"] = ["tv", "android"]

    # Tezlik uchun (fragment parallel)
    opts.update({
        "concurrent_fragment_downloads": 4,
        "fragment_retries": 10,
        "retries": 10,
        "socket_timeout": 30,
    })

    return opts


def download_video(
    url: str,
    quality_key: str,
    tmp_dir: str | Path,
    max_file_bytes: int,
    progress_cb: Optional[ProgressCallback] = None,
    user_agent: Optional[str] = None,
    cookies_path: Optional[Path] = None,
) -> DownloadResult:
    """Download a video with yt-dlp.

    Args:
        url: Video URL (YouTube/Instagram).
        quality_key: One of QUALITY_MAP keys.
        tmp_dir: Directory to place the downloaded file.
        max_file_bytes: Maximum allowed file size.
        progress_cb: Optional callback receiving yt-dlp progress dicts.
        user_agent: Optional custom user-agent.
        cookies_path: Optional path to cookies file for yt-dlp.

    Raises:
        UnsupportedURLError: If URL domain is not allowed.
        FileTooLargeError: If expected or actual size exceeds the limit.
        DownloadFailedError: For other yt-dlp errors.

    Returns:
        DownloadResult with file_path, title, ext, and size.
    """

    if not SUPPORTED_DOMAINS.match(url):
        raise UnsupportedURLError("Only YouTube and Instagram URLs are supported.")

    tmp_path = Path(tmp_dir)
    tmp_path.mkdir(parents=True, exist_ok=True)

    ydl_opts = _build_opts(url, quality_key, tmp_path, max_file_bytes, progress_cb, user_agent, cookies_path)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            est_size = _estimate_size(info)
            if est_size and est_size > max_file_bytes:
                raise FileTooLargeError(
                    f"Estimated file size {est_size} exceeds limit {max_file_bytes}. "
                    "Try a lower quality."
                )

            info = ydl.extract_info(url, download=True)
            if "requested_downloads" in info:
                downloaded = info["requested_downloads"][0]
                file_path = Path(downloaded["filepath"])
                size = downloaded.get("filesize") or file_path.stat().st_size
                title = downloaded.get("title") or info.get("title") or file_path.stem
                ext = downloaded.get("ext") or file_path.suffix.lstrip(".")
            else:
                file_path = Path(ydl.prepare_filename(info))
                size = file_path.stat().st_size
                title = info.get("title") or file_path.stem
                ext = file_path.suffix.lstrip(".")

            if size > max_file_bytes:
                raise FileTooLargeError(
                    f"Downloaded file size {size} exceeds limit {max_file_bytes}. Try a lower quality."
                )

            return DownloadResult(file_path=file_path, title=title, ext=ext, size=size)
    except FileTooLargeError:
        raise
    except UnsupportedURLError:
        raise
    except Exception as exc:  # yt-dlp raises generic exceptions
        raise DownloadFailedError(str(exc)) from exc
