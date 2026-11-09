"""Offline contract tests for the Zalo adapter; no Bot API calls."""

import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from zalo_bot import Update
from zalo_bot.error import InvalidToken

import access
import bot_zalo
import config
import main


def update(text: str, *, message_id="m1", user_id="u1", chat_id="c1",
           chat_type="PRIVATE", event="message.text.received", is_bot=False,
           display_name=None):
    return Update.de_json({
        "event_name": event,
        "message": {
            "message_id": message_id, "date": 1750316131602,
            "message_type": "CHAT_TEXT", "text": text,
            "from": {"id": user_id, "is_bot": is_bot, "display_name": display_name},
            "chat": {"id": chat_id, "chat_type": chat_type},
        }}, None)


class ZaloAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.adapter = bot_zalo.ZaloAdapter(self.bot, bot_id="bot", group_enabled=True)

    async def test_sdk_update_dedupe_and_self_message(self):
        await self.adapter.handle_update(update("/id"))
        await self.adapter.handle_update(update("/id"))
        await self.adapter.handle_update(update("/id", message_id="m2", is_bot=True))
        await self.adapter.handle_update(update("/id", message_id="m3", user_id="bot"))
        await self.adapter.handle_update(update("/id", message_id="m4", event="message.image.received"))
        self.bot.send_message.assert_awaited_once_with(chat_id="c1", text="Zalo user ID của bạn: u1")

    async def test_winner_and_score_use_profile_name_without_exposing_id(self):
        for number, (text, user_id, name) in enumerate((
            ("/batdau", "private-id-x", "Minh"),
            ("/thamgia", "private-id-o", "Lan"),
            ("/dauhang", "private-id-o", "Lan"),
            ("/diemcaro", "private-id-x", "Minh"),
        )):
            await self.adapter.handle_update(update(text, message_id=str(number + 1),
                                                   user_id=user_id, display_name=name))
        result = self.bot.send_message.await_args_list[-2].kwargs["text"]
        self.assertIn("Minh chiến thắng", result)
        self.assertIn("Lan đã đầu hàng", result)
        for call in self.bot.send_message.await_args_list:
            self.assertNotIn("private-id-", call.kwargs["text"])

    async def test_missing_profile_name_uses_neutral_label(self):
        await self.adapter.handle_update(update("/batdau", message_id="n1", user_id="secret-id"))
        await self.adapter.handle_update(update("/choibot", message_id="n2", user_id="secret-id"))
        await self.adapter.handle_update(update("/dauhang", message_id="n3", user_id="secret-id"))
        message = self.bot.send_message.await_args.kwargs["text"]
        self.assertIn("Người chơi đã đầu hàng", message)
        self.assertNotIn("secret-id", message)

    async def test_admin_gate_and_shared_core(self):
        with patch.dict(os.environ, {"ZALO_ADMIN_IDS": "admin-1"}), \
             patch.object(bot_zalo.core, "create_problem", return_value=True) as create, \
             patch.object(bot_zalo.storage, "record_admin_event") as audit:
            await self.adapter.handle_text("c", "u", "/create demo")
            create.assert_not_called()
            await self.adapter.handle_text("c", "admin-1", "/create demo")
            create.assert_called_once_with("demo", "admin-1")
            audit.assert_called_once_with("zalo", "admin-1", "create", "demo")
            self.assertTrue(access.admin_id("zalo", "admin-1"))

    async def test_code_session_isolated_ordered_and_cancelled(self):
        with patch.object(self.adapter, "_execute", new_callable=AsyncMock) as execute:
            await self.adapter.handle_text("c", "u1", "/submit demo", now=1)
            await self.adapter.handle_text("c", "u2", "/run", now=1)
            await self.adapter.handle_text("c", "u1", "  int main() {", now=2)
            await self.adapter.handle_text("c", "u1", "return 0;\n}", now=3)
            await self.adapter.handle_text("c", "u2", "/cancel", now=4)
            await self.adapter.handle_text("c", "u1", "/done", now=5)
            execute.assert_awaited_once_with("c", "u1", "submit", "demo", "int main() {\nreturn 0;\n}")
            self.assertFalse(self.adapter.sessions)

    async def test_code_session_expiry_and_limit(self):
        with patch.object(self.adapter, "_execute", new_callable=AsyncMock) as execute:
            await self.adapter.handle_text("c", "u", "/run", now=1)
            await self.adapter.handle_text("c", "u", "x" * (access.MAX_CODE_BYTES + 1), now=2)
            self.assertFalse(self.adapter.sessions)
            await self.adapter.handle_text("c", "u", "/run", now=3)
            await self.adapter.handle_text("c", "u", "/done", now=3 + bot_zalo.SESSION_SECONDS + 1)
            execute.assert_not_awaited()

    async def test_judge_event_routing(self):
        async def judge(*args):
            yield {"t": "status", "msg": "compiling"}
            yield {"t": "wa", "test": 2, "inp": "1\n", "sol": "2\n", "out": "3\n"}

        with patch.object(bot_zalo.core, "judge", judge):
            await self.adapter.handle_text("c", "u", "/submit demo int main(){}")
        sent = [call.kwargs["text"] for call in self.bot.send_message.await_args_list]
        self.assertEqual(len(sent), 2)
        self.assertIn("test 2", sent[1])
        self.assertIn("Output mong đợi:\n2", sent[1])

    async def test_run_uses_user_input_and_group_limited_to_commands(self):
        with patch.object(bot_zalo.core, "get_user_input", return_value="42") as inp, \
             patch.object(bot_zalo.core, "run_once", new_callable=AsyncMock,
                          return_value={"t": "ok", "output": "84"}) as run:
            await self.adapter.handle_update(update("/run int main(){}", chat_type="GROUP"))
            inp.assert_called_once_with("zalo:u1")
            run.assert_awaited_once_with("int main(){}", "42")
            await self.adapter.handle_update(update("/run", message_id="m2", chat_type="GROUP"))
            self.assertFalse(self.adapter.sessions)

    async def test_message_chunks_and_statuses(self):
        value = "đề bài\n" + "a\u0301" * 2000 + "\n" + "x" * 2500
        chunks = bot_zalo.split_message(value)
        self.assertEqual("".join(chunks), value)
        self.assertTrue(all(0 < len(chunk) <= 1850 for chunk in chunks))
        await self.adapter.send("c", value)
        self.assertEqual(len(self.bot.send_message.await_args_list), len(chunks))
        self.assertIn("Accepted (AC): bài p đã qua 3 test.",
                      bot_zalo.format_result({"t": "ac", "count": 3}, "p"))
        for event in ({"t": "ce", "who": "checker", "stderr": "bad"},
                      {"t": "rte", "test": 1}, {"t": "tle", "test": 1},
                      {"t": "sys", "msg": "gen_tle"}, {"t": "not_found"}):
            self.assertTrue(bot_zalo.format_result(event, "p"))

    async def test_polling_cancellation_closes_sdk(self):
        closed = asyncio.Event()

        class FakeBot:
            def __init__(self, token):
                self.token = token

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                closed.set()

            async def get_me(self):
                return SimpleNamespace(id="bot", can_join_groups=False)

            async def get_update(self, **kwargs):
                await asyncio.Event().wait()

        with patch.object(bot_zalo, "Bot", FakeBot):
            task = asyncio.create_task(bot_zalo.run_zalo_bot("fake"))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(closed.is_set())


class ZaloGameTests(unittest.IsolatedAsyncioTestCase):
    async def test_games_load_dispatch_and_state_per_chat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "zalo.sample"
            folder.mkdir()
            (folder / "der.json").write_text(json.dumps({"commands": {
                "play1": {"description": "test game", "handler": "game.py:play"},
                "score": {"description": "show score", "handler": "game.py:score"},
            }}), encoding="utf-8")
            (folder / "game.py").write_text(
                "async def play(ctx):\n"
                "    ctx.state[ctx.user_id] = ctx.state.get(ctx.user_id, 0) + 1\n"
                "    await ctx.reply(f'played {ctx.args}: {ctx.state[ctx.user_id]}')\n"
                "def score(ctx):\n"
                "    return str(ctx.state.get(ctx.user_id, 0))\n",
                encoding="utf-8")
            bot = SimpleNamespace(send_message=AsyncMock())
            adapter = bot_zalo.ZaloAdapter(bot, games_root=root)
            await adapter.handle_text("chat1", "user", "/play1 first")
            await adapter.handle_text("chat1", "user", "/play1 second")
            await adapter.handle_text("chat1", "user", "/score")
            await adapter.handle_text("chat2", "user", "/score")
            await adapter.handle_text("chat1", "user", "/help sample")
            sent = [call.kwargs["text"] for call in bot.send_message.await_args_list]
            self.assertEqual(sent[:4], ["played first: 1", "played second: 2", "2", "0"])
            self.assertIn("/play1: test game", sent[4])

    async def test_invalid_game_is_skipped_without_hiding_other_games(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder_name, command, handler in (
                ("zalo.bad", "help", "game.py:run"),
                ("zalo.good", "hello", "game.py:run"),
                ("zalo.unsafe", "unsafe", "../outside.py:run"),
            ):
                folder = root / folder_name
                folder.mkdir()
                (folder / "der.json").write_text(json.dumps({"commands": {
                    command: {"description": "demo", "handler": handler}
                }}), encoding="utf-8")
                (folder / "game.py").write_text("def run(ctx):\n    return 'ok'\n", encoding="utf-8")
            bot = SimpleNamespace(send_message=AsyncMock())
            adapter = bot_zalo.ZaloAdapter(bot, games_root=root)
            self.assertEqual(set(adapter.games), {"hello"})
            await adapter.handle_text("c", "u", "/hello")
            bot.send_message.assert_awaited_once_with(chat_id="c", text="ok")


class ZaloLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_token_is_terminal(self):
        attempts = []

        class RejectedBot:
            def __init__(self, token):
                attempts.append(1)

            async def __aenter__(self):
                raise InvalidToken("rejected")

            async def __aexit__(self, *args):
                pass

        with patch.object(bot_zalo, "Bot", RejectedBot), patch.object(bot_zalo.LOG, "error"):
            await bot_zalo.run_zalo_bot("fake")
        self.assertEqual(len(attempts), 1)

    async def test_config_and_missing_token(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "DISCORD_TOKEN": "",
                                  "ZALO_BOT_TOKEN": "fake"}), \
             patch.object(config.shutil, "which", return_value="g++"):
            errors, _ = config.check_config()
            self.assertEqual(errors, [])
        with patch.object(main, "RUN_ZALO", False), patch.object(main, "RUN_DISCORD", False), \
             patch.object(main, "RUN_TELEGRAM", False), patch("builtins.print"):
            with self.assertRaises(SystemExit):
                await main.main()

    async def test_main_without_zalo_and_three_bot_cancellation(self):
        with patch.object(main, "RUN_ZALO", False), patch.object(main, "RUN_DISCORD", False), \
             patch.object(main, "RUN_TELEGRAM", True), patch.object(main, "run_telegram",
             new_callable=AsyncMock) as telegram, patch("builtins.print"):
            await main.main()
            telegram.assert_awaited_once()

        entered = set()

        async def waiting(name):
            entered.add(name)
            await asyncio.Event().wait()

        with patch.object(main, "RUN_ZALO", True), patch.object(main, "RUN_DISCORD", True), \
             patch.object(main, "RUN_TELEGRAM", True), \
             patch.object(main, "run_zalo", new=lambda: waiting("zalo")), \
             patch.object(main, "run_discord", new=lambda: waiting("discord")), \
             patch.object(main, "run_telegram", new=lambda: waiting("telegram")), \
             patch("builtins.print"):
            task = asyncio.create_task(main.main())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertEqual(entered, {"discord", "telegram", "zalo"})
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    unittest.main()
