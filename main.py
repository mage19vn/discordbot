import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

RUN_DISCORD = os.getenv("DISCORD_TOKEN", "").strip() != ""
RUN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() != ""


async def run_discord():
    import bot_discord

    bot = bot_discord.create_bot()
    await bot.start(bot_discord.TOKEN)


async def run_telegram():
    import bot_telegram

    app = bot_telegram.create_app()
    bot_telegram.register_handlers(app)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


async def main():
    tasks = []
    if RUN_DISCORD:
        tasks.append(asyncio.create_task(run_discord(), name="discord"))
    else:
        print("Bỏ qua Discord: chưa có DISCORD_TOKEN.")
    if RUN_TELEGRAM:
        print("Chạy Telegram...")
        tasks.append(asyncio.create_task(run_telegram(), name="telegram"))
    else:
        print("Bỏ qua Telegram: chưa có TELEGRAM_BOT_TOKEN.")
    if not tasks:
        raise SystemExit("Cần ít nhất một token (DISCORD_TOKEN hoặc TELEGRAM_BOT_TOKEN).")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
