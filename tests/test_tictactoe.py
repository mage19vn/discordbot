"""Offline game rules and plugin contract checks."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from zalo_games import load_games


class TicTacToeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commands = load_games(Path(__file__).resolve().parents[1], set())

    def setUp(self):
        self.state = {}

    def call(self, command, user="x", args="", state=None):
        ctx = SimpleNamespace(user_id=user, display_name=user, args=args,
                              state=self.state if state is None else state)
        return self.commands[command].handler(ctx)

    def two_players(self):
        self.call("batdau")
        self.call("thamgia", "o")

    def test_two_players_win_and_restart(self):
        self.two_players()
        for user, cell in (("x", "1"), ("o", "4"), ("x", "2"),
                           ("o", "5"), ("x", "3")):
            result = self.call("chono", user, cell)
        self.assertIn("x chiến thắng", result)
        board = self.state["game"]["board"][:]
        self.call("chono", "o", "6")
        self.assertEqual(board, self.state["game"]["board"])
        self.call("batdau", "o")
        self.assertEqual(self.state["game"]["players"], {"X": "o"})
        self.assertEqual(self.state["game"]["board"], [""] * 9)

    def test_draw(self):
        self.two_players()
        for index, cell in enumerate((1, 2, 3, 5, 4, 6, 8, 7, 9)):
            result = self.call("chono", "x" if index % 2 == 0 else "o", str(cell))
        self.assertIn("hòa", result)
        self.assertEqual(self.state["game"]["status"], "finished")

    def test_rejected_actions_do_not_mutate_game(self):
        self.two_players()
        before = deepcopy(self.state)
        for command, user, args in (("batdau", "stranger", ""),
                                    ("thamgia", "stranger", ""),
                                    ("chono", "stranger", "1"),
                                    ("chono", "o", "1"),
                                    ("chono", "x", ""),
                                    ("chono", "x", "0"),
                                    ("chono", "x", "10"),
                                    ("chono", "x", "1 2"),
                                    ("dungcaro", "o", "")):
            self.call(command, user, args)
            self.assertEqual(self.state, before)
        self.call("chono", "x", "1")
        before = deepcopy(self.state)
        self.call("chono", "o", "1")
        self.assertEqual(self.state, before)

    def test_chat_isolation_and_host_controls(self):
        self.call("batdau")
        other = {}
        self.call("batdau", "another", state=other)
        before = deepcopy(self.state)
        self.call("choibot", "stranger")
        self.call("thamgia", "x")
        self.assertEqual(before, self.state)
        self.call("choibot")
        self.call("chono", args="1")
        self.assertEqual(other["game"]["board"], [""] * 9)
        self.call("dungcaro")
        self.assertIn("game", self.state)  # Active games must end through surrender.
        self.call("dauhang")
        self.call("dungcaro")
        self.assertNotIn("game", self.state)
        self.assertEqual(self.state["scores"]["x"]["loss"], 1)

    def test_rematch_requires_both_players_and_scores_once(self):
        self.two_players()
        self.call("dauhang", "o")
        self.call("dauhang", "o")
        self.assertEqual(self.state["scores"]["x"]["win"], 1)
        self.call("choilai", "stranger")
        self.assertEqual(self.state["game"]["rematch"], [])
        self.call("choilai", "x")
        self.call("choilai", "x")
        self.assertEqual(self.state["game"]["status"], "finished")
        self.call("choilai", "o")
        self.assertEqual(self.state["game"]["status"], "playing")
        self.assertEqual(self.state["game"]["board"], [""] * 9)
        self.assertEqual(self.state["scores"]["x"]["win"], 1)

    def test_expired_lobby_can_be_replaced_and_show_does_not_extend_it(self):
        with patch("time.monotonic", return_value=1):
            self.call("batdau")
        with patch("time.monotonic", return_value=500):
            self.call("banco")
            self.assertEqual(self.state["game"]["updated_at"], 1)
        with patch("time.monotonic", return_value=902):
            self.call("batdau", "new")
            self.assertEqual(self.state["game"]["players"], {"X": "new"})

    def test_bot_levels_and_invalid_choice(self):
        self.call("batdau")
        self.call("choibot", args="invalid")
        self.assertEqual(self.state["game"]["status"], "waiting")
        self.call("choibot", args="de")
        self.assertEqual(self.state["game"]["level"], "de")
        self.call("chono", args="5")
        self.assertEqual(self.state["game"]["board"].count("O"), 1)

    def test_bot_never_loses_against_any_human_sequence(self):
        self.call("batdau")
        self.call("choibot")

        def explore(state):
            for cell, mark in enumerate(state["game"]["board"]):
                if mark:
                    continue
                branch = deepcopy(state)
                result = self.call("chono", args=str(cell + 1), state=branch)
                self.assertNotEqual(branch["game"].get("winner"), "X")
                game = branch["game"]
                if game["status"] == "playing":
                    self.assertEqual(game["turn"], "X")
                    self.assertEqual(game["board"].count("X"), game["board"].count("O"))
                    explore(branch)

        explore(self.state)


if __name__ == "__main__":
    unittest.main()
