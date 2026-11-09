"""Check the chat help menu and shared guessing-game lifecycle offline."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot_zalo import ZaloAdapter
from zalo_games import load_games


class GuessingGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commands = load_games(Path(__file__).resolve().parents[1], set())

    def setUp(self):
        self.state = {}

    def call(self, command, user="host", args=""):
        return self.commands[command].handler(SimpleNamespace(
            user_id=user, display_name=user, args=args, state=self.state))

    def start(self):
        with patch("random.randint", return_value=10):
            self.call("doanso")

    def test_cannot_overwrite_or_stop_another_players_round(self):
        self.start()
        before = deepcopy(self.state)
        self.call("doanso", "guest")
        self.call("boquadoanso", "guest")
        for args in ("", "hello", "0", "11"):
            self.call("doso", args=args)
        self.assertEqual(before, self.state)
        self.call("doso", "guest", "5")
        self.assertEqual(self.state["remaining"], 4)
        self.call("doso", args="5")
        self.assertEqual(self.state["remaining"], 4)
        result = self.call("doso", "guest", "10")
        self.assertIn("guest", result)
        self.assertFalse(self.state)

    def test_attempt_limit_and_expiry(self):
        self.start()
        for value in range(1, 6):
            result = self.call("doso", args=str(value))
        self.assertIn("Đáp án là 10", result)
        self.assertFalse(self.state)
        with patch("time.monotonic", return_value=1):
            self.start()
        with patch("time.monotonic", return_value=902):
            self.call("doso", args="10")
            self.assertFalse(self.state)


class HelpFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_game_topics_and_command_topics(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        adapter = ZaloAdapter(bot)
        await adapter.handle_text("c", "u", "/help")
        self.assertIn("/games", bot.send_message.await_args.kwargs["text"])
        await adapter.handle_text("c", "u", "/games")
        self.assertIn("Tic Tac Toe", bot.send_message.await_args.kwargs["text"])
        for topic in ("tictactoe", "chono", "zalo.tictactoe"):
            await adapter.handle_text("c", "u", f"/help {topic}")
            message = bot.send_message.await_args.kwargs["text"]
            self.assertIn("/carohelp", message)
            self.assertIn("/choilai", message)
        await adapter.handle_text("c", "u", "/help cpp")
        self.assertIn("/submit", bot.send_message.await_args.kwargs["text"])
        await adapter.handle_text("c", "u", "/help unknown")
        self.assertIn("/games", bot.send_message.await_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
