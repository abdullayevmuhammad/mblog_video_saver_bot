# bot.py
"""Telegram bot entrypoint for video saving."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ensure_directories, get_settings, setup_logging
from downloader import (
    SUPPORTED_DOMAINS,
    DownloadFailedError,
    DownloadResult,
    FileTooLargeError,
    UnsupportedURLError,
    download_video,
)
from utils import human_readable_size, is_member, run_blocking, safe_remove

settings = get_settings()
ensure_directories(settings)
setup_logging(settings.log_level, Path("logs/bot.log"))

bot = Bot(token=settings.bot_token)
dp = Dispatcher()
logger = logging.getLogger(__name__)

# Channel target: can be numeric id or @username
CHANNEL_TARGET = settings.channel_reference

if isinstance(CHANNEL_TARGET, str) and CHANNEL_TARGET.startswith("@"):
    CHANNEL_PROMPT = f"⛔️ Avval {CHANNEL_TARGET} kanaliga a'zo bo'ling, so'ngra urinib ko'ring."
else:
    CHANNEL_PROMPT = "⛔️ Avval kanalga a'zo bo'ling, so'ngra urinib ko'ring."

QUALITY_ORDER = ["360p", "480p", "720p", "1080p", "best", "mp3"]

URL_RE = re.compile(r"https?://\S+")

# URL cache: URLlar juda uzun bo'lgani uchun callback_data ga sig'maydi.
# Shu sababli qisqa ID ishlatamiz.
_url_cache: dict[str, str] = {}
_url_counter = 0


def _store_url(url: str) -> str:
    """URL ni cache ga saqlaydi va qisqa ID qaytaradi."""
    global _url_counter
    _url_counter += 1
    key = f"u{_url_counter}"
    _url_cache[key] = url
    return key


def _get_url(key: str) -> str | None:
    """Cache dan URL ni oladi."""
    return _url_cache.get(key)


def quality_keyboard(url: str) -> InlineKeyboardMarkup:
    url_key = _store_url(url)
    buttons = [
        InlineKeyboardButton(text=q.upper(), callback_data=f"DL|{url_key}|{q}") for q in QUALITY_ORDER
    ]
    rows = [[b] for b in buttons]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _parse_url_from_command(message: Message) -> str | None:
    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        return None
    return parts[1].strip()


def extract_url_from_message(message: Message) -> str | None:
    # 1) entities
    if message.entities:
        for ent in message.entities:
            if ent.type in ("url", "text_link"):
                if ent.type == "text_link":
                    return ent.url
                else:
                    return message.text[ent.offset: ent.offset + ent.length]
    # 2) fallback regex
    if message.text:
        m = URL_RE.search(message.text)
        if m:
            return m.group(0)
    return None


def sanitize_url(url: str) -> str:
    clean = url.strip()
    if "youtube" in clean or "youtu.be" in clean:
        clean = clean.split("&", 1)[0]
    if "instagram" in clean or "instagr.am" in clean:
        clean = clean.split("?", 1)[0]
    return clean


async def prompt_for_quality(message: Message, url: str, intro_text: str | None = None) -> None:
    clean_url = sanitize_url(url)
    if not SUPPORTED_DOMAINS.match(clean_url):
        await message.answer("Faqat YouTube yoki Instagram havolasini yuboring.")
        return

    member = await is_member(bot, CHANNEL_TARGET, message.from_user.id)
    if not member:
        await message.answer(CHANNEL_PROMPT)
        return

    prompt = "Qaysi sifatda yuklaymiz?"
    if intro_text:
        prompt = f"{intro_text}\n{prompt}"

    await message.answer(prompt, reply_markup=quality_keyboard(clean_url))


@dp.message(Command(commands=["start", "help"]))
async def handle_start(message: Message) -> None:
    await message.answer(
        "👋 Assalomu alaykum! Menga YouTube yoki Instagram link yuboring"
    )


@dp.message(Command(commands=["download"]))
async def handle_download_command(message: Message) -> None:
    url = _parse_url_from_command(message)
    if not url:
        await message.answer("Linkni yuboring")
        return

    await prompt_for_quality(message, url)

    try:
        await message.delete()
    except Exception:
        pass



# Catch plain messages that may contain URLs
@dp.message(F.text)
async def handle_any_message(message: Message) -> None:
    if message.text and message.text.startswith("/"):
        return

    url = extract_url_from_message(message)
    if not url:
        await message.answer("Iltimos, YouTube yoki Instagram havolasini yuboring.")
        return

    # 1) Avval tugmalarni chiqaramiz
    await prompt_for_quality(message, url)

    # 2) Keyin user link xabarini o'chiramiz (xato bo'lsa ham bot ishlashda davom etadi)
    try:
        await message.delete()
    except Exception:
        pass


@dp.callback_query(F.data.startswith("DL|"))
async def handle_download_callback(callback: CallbackQuery) -> None:
    parts = callback.data.split("|", 2)
    if len(parts) != 3:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    _, url_key, quality = parts
    url = _get_url(url_key)
    if not url:
        await callback.answer("Link eskirgan. Qaytadan yuboring.", show_alert=True)
        return

# Tugmalarni olib tashlab, tanlangan sifatni ko‘rsatish
    try:
        await callback.message.edit_text(
            f"✅ Tanlandi: {quality.upper()}\nYuklab olinmoqda…",
            reply_markup=None,
        )
    except Exception:
        pass


    member = await is_member(bot, CHANNEL_TARGET, callback.from_user.id)
    if not member:
        await callback.message.answer(CHANNEL_PROMPT)
        return

    progress_msg = await callback.message.answer("Yuklanmoqda…")

    loop = asyncio.get_running_loop()
    last_update = {"ts": 0.0}

    async def throttled_edit(text: str) -> None:
        now = time.monotonic()
        if now - last_update["ts"] < 1.5:  # throttle to reduce spam
            return
        last_update["ts"] = now
        try:
            await progress_msg.edit_text(text)
        except Exception:
            pass

    def progress_cb(data: dict) -> None:
        if data.get("status") != "downloading":
            return
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        downloaded = data.get("downloaded_bytes") or 0
        if not total:
            return
        percent = downloaded / total * 100
        text = (
            f"Yuklanmoqda: {percent:.1f}%\n"
            f"{human_readable_size(downloaded)} / {human_readable_size(int(total))}"
        )
        loop.call_soon_threadsafe(asyncio.create_task, throttled_edit(text))

    tmp_dir = settings.download_path / f"dl_{callback.from_user.id}_{int(time.time())}"

    try:
        result: DownloadResult = await run_blocking(
            download_video,
            url,
            quality,
            tmp_dir,
            settings.max_file_bytes,
            progress_cb,
            settings.ytdlp_user_agent,
            settings.ytdlp_cookies_path,
            loop=loop,
        )
    except UnsupportedURLError:
        await progress_msg.edit_text("Bu link qo'llab-quvvatlanmaydi. Faqat YouTube yoki Instagram.")
        safe_remove(tmp_dir)
        return
    except FileTooLargeError as exc:
        await progress_msg.edit_text(
            f"Fayl juda katta. {human_readable_size(settings.max_file_bytes)} limit. Tafsilot: {exc}"
        )
        safe_remove(tmp_dir)
        return
    except DownloadFailedError as exc:
        await progress_msg.edit_text(f"Yuklab olishda xatolik: {exc}")
        safe_remove(tmp_dir)
        return
    except Exception:
        await progress_msg.edit_text("Kutilmagan xatolik yuz berdi. Keyinroq urinib ko'ring.")
        safe_remove(tmp_dir)
        return

    try:
        # Telegram video limit ~2GB; aiogram handles but we enforce our own.
        if result.size > settings.max_file_bytes:
            await progress_msg.edit_text(
                "Fayl Telegram chegarasidan katta. Pastroq sifatni tanlang yoki boshqa video tanlang."
            )
            safe_remove(tmp_dir)
            return

        file = FSInputFile(path=result.file_path, filename=f"{result.title}.{result.ext}")
        caption = f"✅ Yuklandi: {result.title}\n🔗 {url}\n@mbloguzar"
        if result.ext == "mp3":
            await bot.send_audio(chat_id=callback.from_user.id, audio=file, caption=caption)
        else:
            await bot.send_video(chat_id=callback.from_user.id, video=file, caption=caption)
        await progress_msg.delete()
    except Exception:
        await progress_msg.edit_text("Video jo'natishda xatolik. Keyinroq urinib ko'ring.")
    finally:
        safe_remove(tmp_dir)


def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN bo'sh. Iltimos .env faylni to'ldiring.")

    # If settings provided username but not numeric id, we attempt to resolve it
    # (useful for initial config: put CHANNEL_USERNAME=@mbloguzar in .env)
    async def _maybe_resolve_username():
        global CHANNEL_TARGET
        if CHANNEL_TARGET is not None and isinstance(CHANNEL_TARGET, str) and CHANNEL_TARGET.startswith("@"):
            try:
                chat = await bot.get_chat(CHANNEL_TARGET)
                CHANNEL_TARGET = chat.id
            except Exception as exc:
                # resolution failed; keep CHANNEL_TARGET as username for is_member resolution
                logger.warning("Kanal username (%s) ni aniqlab bo'lmadi: %s", CHANNEL_TARGET, exc)

    # resolve before polling
    asyncio.run(_maybe_resolve_username())

    if CHANNEL_TARGET is None:
        raise RuntimeError(
            "Kanal identifikatori topilmadi. Iltimos .env faylga CHANNEL_ID (raqam) yoki CHANNEL_USERNAME (@username) qo'ying."
        )

    dp.run_polling(bot)


if __name__ == "__main__":
    main()
