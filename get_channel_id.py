# get_channel_id.py
import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot

load_dotenv()

async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN topilmadi. Iltimos .env faylga BOT_TOKEN ni qo'ying.")
    username = os.getenv("CHANNEL_USERNAME")
    if not username:
        raise RuntimeError("CHANNEL_USERNAME topilmadi. .env faylga CHANNEL_USERNAME=@your_channel qo'ying.")
    bot = Bot(token=token)
    try:
        chat = await bot.get_chat(username)
        print("Channel numeric id:", chat.id)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
