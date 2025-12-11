# config.py
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    bot_token: str
    channel_id: Optional[int]
    channel_username: Optional[str]
    download_path: Path
    max_file_bytes: int
    log_level: str
    ytdlp_user_agent: Optional[str] = None
    ytdlp_cookies_path: Optional[Path] = None

    @property
    def channel_reference(self) -> Optional[int | str]:
        """
        Return channel id (preferred) or username if id not provided.
        This order ensures numeric id is used when available.
        """
        return self.channel_id if self.channel_id is not None else self.channel_username


def _get_env_int(name: str, default: Optional[int]) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer (got: {raw!r})") from exc


def _normalize_channel_username(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if not raw.startswith("@"):
        raw = f"@{raw}"
    return raw


def get_settings() -> Settings:
    download_path = Path(os.getenv("DOWNLOAD_PATH", "tmp")).resolve()
    max_file_bytes = _get_env_int("MAX_FILE_BYTES", 500 * 1024 * 1024) or (500 * 1024 * 1024)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    ytdlp_cookies = os.getenv("YTDLP_COOKIES")
    ytdlp_cookies_path = Path(ytdlp_cookies) if ytdlp_cookies and ytdlp_cookies.strip() else None

    channel_id: Optional[int] = None
    channel_username: Optional[str] = None

    channel_raw = os.getenv("CHANNEL_ID")
    if channel_raw:
        channel_raw = channel_raw.strip()
        if channel_raw.startswith("@"):
            channel_username = _normalize_channel_username(channel_raw)
        elif channel_raw:
            channel_id = _get_env_int("CHANNEL_ID", None)

    if channel_username is None:
        channel_username = _normalize_channel_username(os.getenv("CHANNEL_USERNAME"))

    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        channel_id=channel_id,
        channel_username=channel_username,
        download_path=download_path,
        max_file_bytes=max_file_bytes,
        log_level=log_level,
        ytdlp_user_agent=os.getenv("YTDLP_USER_AGENT"),
        ytdlp_cookies_path=ytdlp_cookies_path,
    )


def setup_logging(log_level: str = "INFO", log_file: Path | None = None) -> None:
    handlers = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def ensure_directories(settings: Settings) -> None:
    settings.download_path.mkdir(parents=True, exist_ok=True)
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
