import asyncio
import concurrent.futures
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

_suite_dir = tempfile.TemporaryDirectory()
os.environ["MAGOJ_DB_PATH"] = str(Path(_suite_dir.name) / "suite.sqlite3")
os.environ["MAGOJ_LEGACY_PATH"] = str(Path(__file__).resolve().parents[1] / "data.json")
os.environ["MAGOJ_JUDGE_BACKEND"] = "local"

import access  # noqa: E402
import bot_telegram  # noqa: E402
import bot_discord  # noqa: E402
import core  # noqa: E402
import config  # noqa: E402
import problem_import  # noqa: E402
import storage  # noqa: E402


class StorageTests(unittest.TestCase):
    def test_json_problem_import_is_atomic_and_private_by_default(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "problem.json"
        parsed = problem_import.parse_problem_json(sample.read_bytes())
        self.assertEqual(parsed[0][0], "NHANDOI")
        self.assertFalse(parsed[0][1]["published"])
        question = parsed[0][1]["question"]
        self.assertIn("# **Nhân đôi một số**\n\n", question)
        self.assertIn("\n\n**Input**\n", question)
        self.assertIn("\n\n**Output**\n", question)
        self.assertIn("\n\n**Điều kiện**\n", question)
        self.assertIn("\n\n**Ví dụ 1**\n\n", question)
        self.assertIn("\n\n**Ví dụ 2**\n\n", question)
        self.assertIn("\n\n**Ghi chú**\n", question)
        rendered = bot_telegram.default_question(question)
        self.assertIn("<b>Input</b>\n", rendered)
        self.assertIn("<b>Output</b>\n", rendered)
        self.assertIn("<pre>3</pre>", rendered)
        headings = [node["children"][0] for node in bot_telegram.question_to_nodes(question)
                    if node.get("tag") == "h3"]
        self.assertTrue(any("Input" in heading for heading in headings))
        self.assertTrue(any("Output" in heading for heading in headings))
        storage.import_problems(parsed, "telegram", "7")
        self.assertIsNone(core.visible_problem("NHANDOI", "telegram", "8"))
        self.assertEqual(storage.get_problem("NHANDOI")["author"], "7")
        second = problem_import.parse_problem_json(
            json.dumps([{"name": "new_in_batch"}, {"name": "NHANDOI"}]).encode())
        with self.assertRaisesRegex(ValueError, "đã tồn tại"):
            storage.import_problems(second, "telegram", "7")
        self.assertIsNone(storage.get_problem("new_in_batch"))

    def test_json_problem_import_validation_and_legacy_format(self):
        with self.assertRaisesRegex(ValueError, "trường không hỗ trợ"):
            problem_import.parse_problem_json(b'{"name":"bad","unexpected":1}')
        with self.assertRaisesRegex(ValueError, "test_count"):
            problem_import.parse_problem_json(b'{"name":"bad","test_count":true}')
        with self.assertRaisesRegex(ValueError, "cần đề"):
            problem_import.parse_problem_json(b'{"name":"bad","published":true}')
        with self.assertRaisesRegex(ValueError, "không dùng cả hai"):
            problem_import.parse_problem_json(b'{"name":"bad","question":"x","statement":{}}')
        with self.assertRaisesRegex(ValueError, "input"):
            problem_import.parse_problem_json(b'{"name":"bad","statement":'
                                              b'{"title":"T","description":"d","output":"o"}}')
        legacy = {"de": {"legacy_json": {"question": "Q", "solution": "S",
                                          "page_url": "old"}}, "inp_data": {"7": "x"}}
        parsed = problem_import.parse_problem_json(json.dumps(legacy).encode())
        self.assertEqual(parsed[0][0], "legacy_json")
        self.assertNotIn("page_url", parsed[0][1])

    def test_legacy_migration_and_sqlite_updates(self):
        legacy = json.loads(Path(os.environ["MAGOJ_LEGACY_PATH"]).read_text(encoding="utf-8"))
        imported = {name for names in storage.list_problems().values() for name in names}
        self.assertTrue(set(legacy["de"]).issubset(imported))
        self.assertEqual(storage.get_problem("BINARYSTRING"), legacy["de"]["BINARYSTRING"])
        self.assertTrue(storage.create_problem("test_store"))
        self.assertFalse(storage.create_problem("test_store"))
        self.assertTrue(storage.set_field("test_store", "category", "Đồ thị"))
        self.assertIn("test_store", storage.list_problems()["Đồ thị"])
        storage.set_input("discord:123", "42")
        self.assertEqual(storage.get_input("discord:123"), "42")
        storage.initialize()
        self.assertEqual(storage.get_problem("test_store")["category"], "Đồ thị")

    def test_history_and_leaderboard(self):
        storage.record_submission("discord", "42", "A", "ac", 123)
        storage.record_submission("discord", "42", "A", "ac", 124)
        storage.record_submission("telegram", "42", "B", "wa", 125)
        self.assertEqual(storage.recent_submissions("discord", "42")[0][2], 124)
        self.assertIn(("discord", "42", 1), storage.leaderboard())

    def test_concurrent_problem_creation(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(storage.create_problem,
                                    (f"concurrent_{i}" for i in range(20))))
        self.assertEqual(results, [True] * 20)
        self.assertTrue(all(storage.get_problem(f"concurrent_{i}") for i in range(20)))

    def test_existing_database_schema_upgrade(self):
        original_db, original_legacy = storage.DB_PATH, storage.LEGACY_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                storage.DB_PATH = Path(tmp) / "old.sqlite3"
                storage.LEGACY_PATH = Path(tmp) / "missing.json"
                with sqlite3.connect(storage.DB_PATH) as db:
                    db.execute("CREATE TABLE submissions (id INTEGER PRIMARY KEY, "
                               "platform TEXT, user_id TEXT, problem TEXT, "
                               "result TEXT, seed INTEGER, created_at TEXT)")
                storage.initialize()
                storage.record_submission("telegram", "1", "A", "wa", 5,
                                          {"inp": "3", "sol": "6"})
                self.assertEqual(storage.last_failure("telegram", "1"),
                                 ("A", 5, "3", "6"))
        finally:
            storage.DB_PATH, storage.LEGACY_PATH = original_db, original_legacy


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_checks(self):
        os.environ["TELEGRAM_ADMIN_IDS"] = "7"
        os.environ["DISCORD_ADMIN_IDS"] = "7"
        self.assertTrue(access.telegram_admin(SimpleNamespace(id=7)))
        self.assertFalse(access.telegram_admin(SimpleNamespace(id=8)))
        self.assertTrue(access.discord_admin(SimpleNamespace(id=7)))
        self.assertFalse(access.discord_admin(
            SimpleNamespace(id=8, guild_permissions=SimpleNamespace(administrator=True))))
        message = SimpleNamespace(text="/create forbidden", reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=8),
                                 effective_message=message, message=message)
        await bot_telegram.create(update, None)
        self.assertIsNone(storage.get_problem("forbidden"))
        message.reply_text.assert_awaited_once()
        allowed_message = SimpleNamespace(text="/create permitted", reply_text=AsyncMock())
        allowed_update = SimpleNamespace(effective_user=SimpleNamespace(id=7),
                                         effective_message=allowed_message,
                                         message=allowed_message)
        await bot_telegram.create(allowed_update, None)
        self.assertIsNotNone(storage.get_problem("permitted"))
        with storage._connect() as db:
            audit = db.execute("SELECT platform,user_id,action FROM admin_events "
                               "WHERE problem='permitted'").fetchone()
        self.assertEqual(audit, ("telegram", "7", "create"))

    async def test_input_limits(self):
        self.assertTrue(access.valid_code("int main(){}"))
        self.assertFalse(access.valid_code("x" * (64 * 1024 + 1)))
        self.assertFalse(access.valid_input("x" * (64 * 1024 + 1)))

    async def test_telegram_input_preview_stays_within_message_limit(self):
        message = SimpleNamespace(text="/input " + "<&>" * 1000,
                                  reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=7))
        await bot_telegram.input_cmd(update, None)
        preview = message.reply_text.await_args.args[0]
        self.assertLess(len(preview), 4096)
        self.assertIn("&lt;&amp;&gt;", preview)
        self.assertTrue(preview.endswith("</pre>"))

    async def test_long_question_preserves_html_sections(self):
        question = "# **Bài dài**\n\n**Input**\n```\n" + "&" * 3000 + "\n```\n\n**Output**\nKết quả"
        body = bot_telegram.default_question(question)
        chunks = list(bot_telegram._html_chunks(body, 3900))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3900 for chunk in chunks))
        self.assertEqual(sum(chunk.count("&amp;") for chunk in chunks), 3000)
        self.assertTrue(all(chunk.count("<pre>") == chunk.count("</pre>") for chunk in chunks))
        self.assertIn("<b>Output</b>", "".join(chunks))
        problem = {"question": question, "test_count": 2,
                   "time_limit": 1, "memory_limit": 64, "version": 3}
        send = AsyncMock()
        with patch.object(core, "visible_problem", return_value=problem), \
             patch.object(bot_telegram, "_get_telegraph_url", new_callable=AsyncMock,
                          return_value=None):
            await bot_telegram._deliver_problem(send, "DEMO", 7)
        sent = [call.args[0] for call in send.await_args_list]
        self.assertGreater(len(sent), 2)
        self.assertTrue(all(len(text) <= 4000 for text in sent))
        self.assertIn("64 MiB", sent[0])

    async def test_config_validation(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "present",
                                  "TELEGRAM_ADMIN_IDS": "bad-id",
                                  "MAGOJ_WEBAPP_URL": "http://example.com",
                                  "MAGOJ_MAX_JOBS": "0"}, clear=True):
            errors, _ = config.check_config()
        self.assertTrue(any("TELEGRAM_ADMIN_IDS" in item for item in errors))
        self.assertTrue(any("MAGOJ_WEBAPP_URL" in item for item in errors))
        self.assertTrue(any("MAGOJ_MAX_JOBS" in item for item in errors))
        self.assertTrue(all("present" not in item for item in errors))

    async def test_cpp_document_submission(self):
        message = SimpleNamespace(
            caption="/submit fixed_only",
            document=SimpleNamespace(file_name="answer.cpp", file_size=18, file_id="file"),
            reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=7))
        remote = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"int main(){}")))
        context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=remote)))
        with patch.object(bot_telegram, "_submit_code", new_callable=AsyncMock) as submit_code:
            await bot_telegram.submit_document(update, context)
            submit_code.assert_awaited_once_with(update, message, "fixed_only", "int main(){}")
        message.document.file_size = access.MAX_CODE_BYTES + 1
        context.bot.get_file.reset_mock()
        await bot_telegram.submit_document(update, context)
        context.bot.get_file.assert_not_awaited()

    async def test_json_document_requires_admin_and_imports(self):
        payload = json.dumps({"name": "from_file", "fixed_tests": ["1"],
                              "test_count": 1}).encode()
        message = SimpleNamespace(
            caption="/importjson", document=SimpleNamespace(
                file_name="problem.json", file_size=len(payload), file_id="file"),
            reply_text=AsyncMock())
        remote = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(payload)))
        context = SimpleNamespace(bot=SimpleNamespace(get_file=AsyncMock(return_value=remote)))
        update = SimpleNamespace(message=message, effective_message=message,
                                 effective_user=SimpleNamespace(id=8),
                                 effective_chat=SimpleNamespace(type="private"))
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "7"}):
            await bot_telegram.submit_document(update, context)
            context.bot.get_file.assert_not_awaited()
            self.assertIsNone(storage.get_problem("from_file"))
            update.effective_user.id = 7
            await bot_telegram.submit_document(update, context)
            self.assertIsNotNone(storage.get_problem("from_file"))
            message.document.file_size = problem_import.MAX_JSON_BYTES + 1
            context.bot.get_file.reset_mock()
            await bot_telegram.submit_document(update, context)
            context.bot.get_file.assert_not_awaited()


class JudgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_compile_run_and_judge(self):
        self.assertEqual((await core.run_once(core.SAMPLE_SOLUTION, "21"))["output"].strip(), "42")
        core.create_problem("judge_test")
        core.set_problem_field("judge_test", "solution", core.SAMPLE_SOLUTION)
        core.set_problem_field("judge_test", "gen_test", core.SAMPLE_GEN)
        events = [event async for event in core.judge(
            "judge_test", core.SAMPLE_SOLUTION, "discord", "100")]
        self.assertEqual(events[-1]["t"], "ac", events)
        self.assertEqual(storage.recent_submissions("discord", "100")[0][2], events[-1]["seed"])
        wrong = "#include<iostream>\nint main(){std::cout<<-1;}"
        events = [event async for event in core.judge("judge_test", wrong)]
        self.assertEqual(events[-1]["t"], "wa", events)
        core.set_problem_field("judge_test", "checker", core.SAMPLE_CHECKER)
        events = [event async for event in core.judge("judge_test", core.SAMPLE_SOLUTION)]
        self.assertEqual(events[-1]["t"], "ac", events)

    async def test_failure_paths(self):
        self.assertEqual((await core.run_once("int main( {", ""))["t"], "ce")
        self.assertEqual((await core.run_once("int main(){return 2;}", ""))["t"], "rte")
        self.assertEqual((await core.run_once("int main(){for(;;){} }", ""))["t"], "tle")
        self.assertEqual((await core.run_once("", ""))["t"], "sys")
        self.assertEqual([e async for e in core.judge("missing", core.SAMPLE_SOLUTION)][-1]["t"],
                         "not_found")

    async def test_fixed_tests_visibility_and_failure_replay(self):
        self.assertTrue(core.create_problem("fixed_only", author="7"))
        core.set_problem_field("fixed_only", "solution", core.SAMPLE_SOLUTION)
        self.assertEqual(core.add_fixed_test("fixed_only", "3\n"), "ok")
        self.assertTrue(core.set_limits("fixed_only", 1, 1, 64))
        self.assertEqual(core.get_problem("fixed_only")["version"], 4)
        self.assertTrue(core.set_problem_field("fixed_only", "published", False))
        self.assertIsNone(core.visible_problem("fixed_only", "telegram", "200"))
        self.assertNotIn("fixed_only", [n for names in core.list_visible_problems(
            "telegram", "200").values() for n in names])
        denied = [e async for e in core.judge("fixed_only", core.SAMPLE_SOLUTION,
                                              "telegram", "200")]
        self.assertEqual(denied[-1]["t"], "not_found")
        wrong = "#include<iostream>\nint main(){std::cout<<0;}"
        events = [e async for e in core.judge("fixed_only", wrong, "telegram", "7")]
        self.assertEqual(events[-1]["t"], "wa", events)
        self.assertEqual(storage.last_failure("telegram", "7")[2:4], ("3\n", "6\n"))
        events = [e async for e in core.judge("fixed_only", core.SAMPLE_SOLUTION,
                                              "telegram", "7")]
        self.assertEqual(events[-1]["t"], "ac", events)
        self.assertEqual(events[-1]["count"], 1)

    async def test_admission_and_secret_environment(self):
        await core._judge_slots.acquire()
        try:
            busy = await core.run_once(core.SAMPLE_SOLUTION, "1")
            self.assertEqual(busy["msg"], "busy")
        finally:
            core._judge_slots.release()
        os.environ["DISCORD_TOKEN"] = "do-not-expose"
        try:
            code = '#include<cstdlib>\n#include<iostream>\nint main(){std::cout<<(getenv("DISCORD_TOKEN")?"leaked":"clean");}'
            result = await core.run_once(code, "")
            self.assertEqual(result["output"], "clean")
        finally:
            del os.environ["DISCORD_TOKEN"]


class DiscordDisplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_statement_keeps_sections_separate(self):
        sample = Path(__file__).resolve().parents[1] / "examples" / "problem.json"
        name, problem = problem_import.parse_problem_json(sample.read_bytes())[0]
        ctx = SimpleNamespace(author=SimpleNamespace(id=7), send=AsyncMock())
        with patch.object(core, "visible_problem", return_value=problem):
            await bot_discord.show.callback(ctx, name=name)
        description = ctx.send.await_args.kwargs["embed"].description
        self.assertIn("**Input**\n", description)
        self.assertIn("\n\n**Output**\n", description)
        self.assertIn("\n\n**Ví dụ 1**\n\n", description)
        self.assertIn("\n\n**Ví dụ 2**\n\n", description)
        self.assertIn("128 MiB", ctx.send.await_args.kwargs["embed"].footer.text)

    async def test_show_and_slash_share_complete_statement(self):
        question = "```cpp\n" + "x" * 8000 + "\n```"
        problem = {"question": question, "test_count": 2,
                   "time_limit": 1, "version": 3}
        ctx = SimpleNamespace(author=SimpleNamespace(id=7), send=AsyncMock())
        with patch.object(core, "visible_problem", return_value=problem):
            await bot_discord.show.callback(ctx, name="DEMO")
        embeds = [call.kwargs["embed"] for call in ctx.send.await_args_list]
        self.assertGreater(len(embeds), 1)
        self.assertTrue(all(len(embed.description) <= 4096 for embed in embeds))
        self.assertIn("2 test", embeds[0].footer.text)
        self.assertIsInstance(ctx.send.await_args_list[0].kwargs["view"],
                              bot_discord.SubmitView)
        self.assertEqual(sum(embed.description.count("x") for embed in embeds), 8000)

        response = SimpleNamespace(send_message=AsyncMock())
        response.is_done = lambda: response.send_message.called
        interaction = SimpleNamespace(user=SimpleNamespace(id=7), response=response,
                                      followup=SimpleNamespace(send=AsyncMock()))
        with patch.object(core, "visible_problem", return_value=problem):
            await bot_discord.slash_problem.callback(interaction, "DEMO")
        response.send_message.assert_awaited()
        self.assertIn("2 test", response.send_message.await_args.kwargs["embed"].footer.text)
        interaction.followup.send.assert_awaited()

    async def test_category_browser_filters_and_paginates(self):
        cats = {f"Category {i:02d}": [f"PROBLEM_{i}"] for i in range(30)}
        self.assertEqual(bot_discord._match_category(cats, "2")[0], "Category 01")
        self.assertEqual(bot_discord._match_category(cats, "category 29")[0], "Category 29")
        ctx = SimpleNamespace(author=SimpleNamespace(id=7), send=AsyncMock())
        with patch.object(core, "list_visible_problems", return_value=cats):
            await bot_discord.problems.callback(ctx, key="29")
        self.assertEqual(ctx.send.await_args.kwargs["view"].category, "Category 28")
        view = bot_discord.ProblemBrowserView(7)
        with patch.object(core, "list_visible_problems", return_value=cats):
            first = view.render()
            self.assertIn("Category 24", first.description)
            self.assertNotIn("Category 25", first.description)
            response = SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock(),
                                       is_done=lambda: False)
            interaction = SimpleNamespace(user=SimpleNamespace(id=7), response=response,
                                          followup=SimpleNamespace(send=AsyncMock()))
            await view.next_page(interaction)
            self.assertIn("Category 29", response.edit_message.await_args.kwargs["embed"].description)
            await view.choose(interaction, "Category 29", None)
            self.assertEqual(view.category, "Category 29")
        with patch.object(core, "list_visible_problems", return_value={"Category 29": ["PROBLEM_29"]}), \
             patch.object(core, "visible_problem", return_value={"question": "Hello"}):
            await view.choose(interaction, "PROBLEM_29", "Category 29")
        response.send_message.assert_awaited()
        self.assertIn("Hello", response.send_message.await_args.kwargs["embed"].description)


if __name__ == "__main__":
    unittest.main()
