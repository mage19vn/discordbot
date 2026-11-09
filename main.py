import asyncio
import os
import sys
import logging
import signal

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from bootstrap import ensure_dependencies
    ensure_dependencies(install="--no-install" not in sys.argv)

from config import check_config

RUN_DISCORD = os.getenv("DISCORD_TOKEN", "").strip() != ""
RUN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() != ""
RUN_ZALO = os.getenv("ZALO_BOT_TOKEN", "").strip() != ""


async def run_discord():
    import bot_discord

    bot = bot_discord.create_bot()
    try:
        await bot.start(bot_discord.TOKEN)
    finally:
        await bot.close()


async def run_telegram():
    import bot_telegram

    app = bot_telegram.create_app()
    bot_telegram.register_handlers(app)
    async with app:
        try:
            await app.start()
            await app.updater.start_polling()
            if app.post_init:
                await app.post_init(app)
            await asyncio.Event().wait()
        finally:
            if app.updater.running:
                await app.updater.stop()
            if app.running:
                await app.stop()


async def run_zalo():
    import bot_zalo

    try:
        await bot_zalo.run_zalo_bot()
    except Exception as exc:
        logging.getLogger(__name__).error("Zalo adapter dừng ngoài dự kiến (%s)", type(exc).__name__)


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
    if RUN_ZALO:
        print("Chạy Zalo...")
        tasks.append(asyncio.create_task(run_zalo(), name="zalo"))
    else:
        print("Bỏ qua Zalo: chưa có ZALO_BOT_TOKEN.")
    if not tasks:
        raise SystemExit("Cần ít nhất một token (DISCORD_TOKEN, TELEGRAM_BOT_TOKEN hoặc ZALO_BOT_TOKEN).")
    def report_failure(task):
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).error("%s dừng (%s); các bot còn lại tiếp tục chạy.",
                                              task.get_name(), type(task.exception()).__name__)

    for task in tasks:
        task.add_done_callback(report_failure)
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        failures = [task.get_name() for task, result in zip(tasks, results)
                    if isinstance(result, BaseException)]
        if failures:
            raise SystemExit("Bot dừng do lỗi: " + ", ".join(failures) + ". Kiểm tra token/quyền và log khởi động.")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def serve():
    """Handle the panel's SIGTERM and release SDK sessions before exiting."""
    task = asyncio.create_task(main())
    loop = asyncio.get_running_loop()
    stopping = False

    def stop():
        nonlocal stopping
        stopping = True
        task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop)
        except (NotImplementedError, RuntimeError):
            pass  # Windows uses asyncio.run's KeyboardInterrupt handling.
    try:
        await task
    except asyncio.CancelledError:
        if not stopping:
            raise


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    errors, warnings = check_config()
    for warning in warnings:
        print("Cảnh báo:", warning)
    if "--check" in sys.argv or "--check-runner" in sys.argv:
        print("Cấu hình:", "OK" if not errors else "CHƯA HỢP LỆ")
    if errors:
        for error in errors:
            print("Lỗi cấu hình:", error)
        raise SystemExit(1)
    if "--check-runner" in sys.argv:
        from healthcheck import check_runner
        ready, message = check_runner()
        print(message)
        raise SystemExit(0 if ready else 1)
    if "--check" in sys.argv:
        raise SystemExit(0)
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
