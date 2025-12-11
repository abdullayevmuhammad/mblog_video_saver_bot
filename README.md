# Vid Saver Bot

Aiogram (v3) Telegram bot that fetches videos from YouTube or Instagram with selectable quality and sends them back to the user. Designed for Python 3.10+.

## Features
- /download <url> command with membership check against your channel.
- Inline quality chooser: 360p, 480p, 720p, 1080p, best.
- Progress updates during download, polite error messages, and cleanup of temp files.
- Size guard against large files; suggests lowering quality when needed.
- Logging to stdout and `logs/bot.log`.

## Requirements
- Python 3.10+.
- Telegram bot token.
- Channel ID where membership is required (e.g., `-1001234567890`).

## Setup (local, Windows PowerShell)
1) Clone or open the project.
2) Create and activate a virtualenv (or reuse `env/` if present):
   ```powershell
   python -m venv env
   .\env\Scripts\Activate.ps1
   ```
3) Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4) Configure environment:
   ```powershell
   Copy-Item .env.example .env
   # Edit .env with your BOT_TOKEN and CHANNEL_ID or CHANNEL_USERNAME
   ```
5) Run the bot:
   ```powershell
   python bot.py
   ```

## Environment variables (.env)
- `BOT_TOKEN`: Telegram bot token (required).
- `CHANNEL_ID`: Channel ID users must be a member of (optional if `CHANNEL_USERNAME` is used).
- `CHANNEL_USERNAME`: Channel username (with leading `@`). Either this or `CHANNEL_ID` must be set.
- `DOWNLOAD_PATH`: Temp storage root (default: `tmp`).
- `MAX_FILE_BYTES`: Max allowed file size in bytes (default: 524288000 ≈ 500MB).
- `LOG_LEVEL`: INFO/DEBUG/WARNING, etc.
- `YTDLP_USER_AGENT`: Optional custom UA for yt-dlp.
- `YTDLP_COOKIES`: Optional path to cookies file for yt-dlp.

## Usage
- Send `/download <youtube_or_instagram_url>` to the bot.
- Pick a quality from the inline buttons.
- If the file would exceed `MAX_FILE_BYTES`, the bot asks you to choose a lower quality.
- Temp folders are created under `DOWNLOAD_PATH` as `dl_<user_id>_<timestamp>/` and removed after sending.

## Tests
Run unit tests (uses pytest):
```powershell
pytest
```

## Notes
- Only YouTube and Instagram URLs are accepted (simple domain check).
- Telegram has an upload limit (~2GB); keep `MAX_FILE_BYTES` within that and your server disk capacity.
- Docker was requested initially but intentionally omitted here per the latest instruction; add a Dockerfile later if needed.

## Commit hint
First commit message suggestion: `feat: initial aiogram video saver implementation`
