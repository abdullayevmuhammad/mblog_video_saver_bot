# utils.py
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logger = logging.getLogger(__name__)


async def is_member(bot: Bot, channel: int | str | None, user_id: int) -> bool:
    """Check whether a user is a member of a channel or supergroup.

    Accepts numeric id or channel username (like '@mbloguzar').
    If username given, resolve it to numeric id first.
    """
    if channel is None:
        logger.debug("Channel identifier missing; cannot verify membership for user %s", user_id)
        return False

    try:
        # if channel is a username, resolve to numeric id
        if isinstance(channel, str) and channel.startswith("@"):
            try:
                chat = await bot.get_chat(channel)
                channel_id = chat.id
            except Exception as exc:
                logger.warning("Failed to resolve channel username %s: %s", channel, exc)
                return False
        else:
            channel_id = channel

        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        status = getattr(member, "status", None)
        logger.info("A'zolik holati: user_id=%s, channel=%s, status=%s", user_id, channel_id, status)
        # 'left' va 'kicked' a'zo emasligini bildiradi
        return status in {"member", "administrator", "creator", "subscriber"}
    except TelegramForbiddenError:
        # Bot is not allowed to access chat members (likely not admin)
        logger.warning("Bot is forbidden to access chat member info for channel=%s", channel)
        return False
    except TelegramBadRequest as exc:
        # e.g., user not found in chat, bad chat id, etc.
        logger.debug("TelegramBadRequest while checking membership: %s", exc)
        return False
    except Exception as exc:
        logger.exception("Unexpected error while checking membership: %s", exc)
        return False


def human_readable_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def safe_remove(path: Path | str) -> None:
    target = Path(path)
    if not target.exists():
        return
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as exc:
        logger.warning("Failed to remove %s: %s", target, exc)


async def run_blocking(func, *args, loop: Optional[asyncio.AbstractEventLoop] = None, **kwargs):
    if loop is None:
        loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
