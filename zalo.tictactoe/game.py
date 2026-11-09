"""Tic-tac-toe for two players or one player against a minimax bot."""

import random
import time

from zalo_ui import card

IDLE_SECONDS = 15 * 60
LEVELS = {"de": "Dễ", "vua": "Vừa", "kho": "Khó"}

LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7),
         (2, 5, 8), (0, 4, 8), (2, 4, 6))
MOVE_ORDER = (4, 0, 2, 6, 8, 1, 3, 5, 7)


def create_message_stage(board):
    cells = [{"X": "❌", "O": "⭕"}.get(mark, f"{i + 1}️⃣") for i, mark in enumerate(board)]
    return "\n".join("  ".join(cells[i:i + 3]) for i in (0, 3, 6))


def _game(ctx):
    game = ctx.state.get("game")
    if game and game["status"] != "finished" and time.monotonic() - game["updated_at"] >= IDLE_SECONDS:
        ctx.state.pop("game")
        return None
    if game and ctx.user_id in game["players"].values():
        _remember_name(ctx)
    return game


def _remember_name(ctx):
    name = getattr(ctx, "display_name", "")
    if name:
        ctx.state.setdefault("names", {})[ctx.user_id] = name


def _label(game, player):
    return game.get("names", {}).get(player, "Người chơi")


def _finish(ctx, game, winner=None, reason=""):
    game["status"] = "finished"
    game["winner"] = winner
    game["reason"] = reason
    game["rematch"] = []
    scores = ctx.state.setdefault("scores", {})
    for mark, player in game["players"].items():
        if game["bot"] and mark == "O":
            continue
        score = scores.setdefault(player, {"win": 0, "draw": 0, "loss": 0})
        score["draw" if winner is None else "win" if winner == mark else "loss"] += 1


def check_winner(board):
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _minimax(board, turn):
    winner = check_winner(board)
    if winner:
        return 1 if winner == "O" else -1
    if all(board):
        return 0
    scores = []
    for index in MOVE_ORDER:
        if not board[index]:
            board[index] = turn
            scores.append(_minimax(board, "X" if turn == "O" else "O"))
            board[index] = ""
    return max(scores) if turn == "O" else min(scores)


def bot_turn(board, level="kho"):
    """Return the best free cell index for O without changing the board."""
    free = [i for i in MOVE_ORDER if not board[i]]
    if not free:
        return None
    if level == "de" or (level == "vua" and random.random() < 0.4):
        return random.choice(free)
    best, best_score = None, -2
    for index in MOVE_ORDER:
        if not board[index]:
            board[index] = "O"
            score = _minimax(board, "X")
            board[index] = ""
            if score > best_score:
                best, best_score = index, score
    return best


def _status(game, note=""):
    board = create_message_stage(game["board"])
    players = "\n".join(f"{'❌' if mark == 'X' else '⭕'} " +
                        ("Bot" if game["bot"] and mark == "O" else _label(game, player))
                        for mark, player in game["players"].items())
    count = sum(bool(mark) for mark in game["board"])
    subtitle = "Tic Tac Toe" + (f" · Bot {LEVELS[game['level']].lower()}" if game["bot"] else "")
    if count:
        subtitle += f" · {count} nước đi"
    body = f"{subtitle}\n\n{players}\n\n{board}"
    if game["status"] == "finished":
        winner = game.get("winner", check_winner(game["board"]))
        if winner:
            player = "Bot" if game["bot"] and winner == "O" else _label(game, game["players"][winner])
            result = f"🏆 {player} chiến thắng!"
        else:
            result = "🤝 Một ván hòa đẹp!"
        if game.get("reason"):
            body += "\n\n" + game["reason"]
        return card(result, body, "/choilai → Tái đấu\n/diemcaro → Xem bảng điểm")
    if game["status"] == "waiting":
        return card("🎮 Ai vào chơi cùng?", body + "\n\nCòn một chỗ cho người cầm ⭕.",
                    "/thamgia → Vào chơi\n/choibot kho → Đấu với bot\n/carohelp → Xem cách chơi")
    turn = game["turn"]
    example = next(i + 1 for i, mark in enumerate(game["board"]) if not mark)
    if note:
        body += "\n\n" + note
    return card(f"🎯 Đến lượt {_label(game, game['players'][turn])}", body,
                f"Chọn một ô còn số, ví dụ /chono {example}\n/carohelp → Trợ giúp")


def start(ctx):
    game = _game(ctx)
    if game and game["status"] != "finished":
        return _status(game)
    _remember_name(ctx)
    game = {"board": [""] * 9, "players": {"X": ctx.user_id},
            "turn": "X", "status": "waiting", "bot": False,
            "level": "kho", "updated_at": time.monotonic(),
            "names": ctx.state.setdefault("names", {})}
    ctx.state["game"] = game
    return _status(game)


def join(ctx):
    game = _game(ctx)
    if not game or game["status"] == "finished":
        return "Chưa có ván chờ. Gõ /batdau để tạo ván."
    if ctx.user_id in game["players"].values():
        return _status(game)
    if game["status"] != "waiting":
        return "Ván cờ đã đủ người chơi."
    game["players"]["O"] = ctx.user_id
    _remember_name(ctx)
    game["status"] = "playing"
    game["updated_at"] = time.monotonic()
    return _status(game, f"{_label(game, ctx.user_id)} đã vào chơi. X đi trước nhé!")


def start_game(ctx):
    """Let the host choose a bot while the game is waiting for player O."""
    game = _game(ctx)
    if not game or game["status"] == "finished":
        return "Gõ /batdau để tạo ván trước."
    if ctx.user_id != game["players"]["X"]:
        return "Chỉ chủ ván (X) được chọn chơi với bot."
    if game["status"] != "waiting":
        return "Ván cờ đã bắt đầu."
    level = ctx.args.strip().lower() or "kho"
    if level not in LEVELS:
        return "⚠️ Chọn mức bot: /choibot de, /choibot vua hoặc /choibot kho."
    game["bot"] = True
    game["players"]["O"] = "Bot"
    game["status"] = "playing"
    game["level"] = level
    game["updated_at"] = time.monotonic()
    return _status(game, "Bạn đi trước. Chúc bạn có một ván cờ hay!")


def make_move(ctx):
    game = _game(ctx)
    if not game or game["status"] == "finished":
        return "Ván cờ chưa bắt đầu hoặc đã kết thúc. Gõ /batdau để tạo ván."
    if game["status"] == "waiting":
        return "Đang chờ người thứ hai. Dùng /thamgia hoặc /choibot."
    if ctx.user_id not in game["players"].values():
        return "Bạn không tham gia ván này."
    if ctx.user_id != game["players"][game["turn"]]:
        return "Chưa đến lượt của bạn."
    value = ctx.args.strip()
    if value not in tuple(str(i) for i in range(1, 10)):
        return "Cú pháp: /chono <số từ 1 đến 9>."
    index = int(value) - 1
    board = game["board"]
    if board[index]:
        return "Ô này đã được đánh. Hãy chọn ô còn trống."
    board[index] = game["turn"]
    game["updated_at"] = time.monotonic()
    if check_winner(board) or all(board):
        _finish(ctx, game, check_winner(board))
        return _status(game)
    game["turn"] = "O" if game["turn"] == "X" else "X"
    prefix = ""
    if game["bot"]:
        index = bot_turn(board, game["level"])
        board[index] = "O"
        prefix = f"Bot vừa chọn ô {index + 1}."
        if check_winner(board) or all(board):
            _finish(ctx, game, check_winner(board))
        else:
            game["turn"] = "X"
    return _status(game, prefix)


def stop(ctx):
    game = _game(ctx)
    if not game:
        return "Chưa có ván cờ."
    if ctx.user_id != game["players"]["X"]:
        return "Chỉ chủ ván (X) được kết thúc ván cờ."
    if game["status"] == "playing":
        return "Ván đang chơi. Dùng /dauhang để kết thúc và ghi nhận kết quả."
    ctx.state.pop("game")
    return card("👋 Đã đóng phòng", "Hẹn bạn ở ván tiếp theo!", "/batdau → Tạo phòng mới")


def show_board(ctx):
    game = _game(ctx)
    return _status(game) if game else "🎮 Chưa có ván cờ hoặc ván đã hết hạn. Gửi /batdau để tạo ván."


def surrender(ctx):
    game = _game(ctx)
    if not game or game["status"] != "playing":
        return "Chưa có ván đang chơi. Gửi /batdau để tạo ván."
    mark = next((mark for mark, player in game["players"].items()
                 if player == ctx.user_id and not (game["bot"] and mark == "O")), None)
    if mark is None:
        return "Bạn không tham gia ván này."
    _finish(ctx, game, "O" if mark == "X" else "X", f"{_label(game, ctx.user_id)} đã đầu hàng.")
    return _status(game)


def rematch(ctx):
    game = _game(ctx)
    if not game or game["status"] != "finished":
        return "Tái đấu chỉ khả dụng sau khi ván kết thúc. Gửi /banco để xem ván hiện tại."
    humans = [player for mark, player in game["players"].items() if not (game["bot"] and mark == "O")]
    if ctx.user_id not in humans:
        return "Chỉ người chơi ván trước được yêu cầu tái đấu."
    if ctx.user_id not in game["rematch"]:
        game["rematch"].append(ctx.user_id)
    pending = [player for player in humans if player not in game["rematch"]]
    if pending:
        return card("🤝 Thêm một ván nữa nhé?", "Đang chờ " + ", ".join(_label(game, user) for user in pending) + " đồng ý.",
                    "/choilai → Nhận lời tái đấu")
    game.update(board=[""] * 9, turn="X", status="playing", winner=None,
                reason="", rematch=[], updated_at=time.monotonic())
    return _status(game, "Ván mới đã sẵn sàng. X đi trước!")


def scoreboard(ctx):
    scores = ctx.state.get("scores", {})
    rows = sorted(scores.items(), key=lambda row: (-row[1]["win"], -row[1]["draw"], row[0]))
    names = ctx.state.get("names", {})
    body = "\n\n".join(f"{['🥇', '🥈', '🥉'][i - 1] if i <= 3 else str(i) + '.'} {names.get(player, 'Người chơi')}\n"
                        f"{s['win']} thắng · {s['draw']} hòa · {s['loss']} thua"
                     for i, (player, s) in enumerate(rows[:10], 1))
    return card("🏆 Những kỳ thủ của phòng", body or "Chưa có kết quả. Hãy chơi ván đầu tiên nhé!",
                "Tic Tac Toe · Điểm trong phiên hiện tại\n/batdau → Tạo ván mới")


def help_game(ctx):
    return card("📖 Chơi Tic Tac Toe thế nào?",
                "Mục tiêu: nối 3 quân theo hàng, cột hoặc đường chéo.\n\n"
                "1. /batdau → tạo phòng, bạn cầm ❌.\n"
                "2. Bạn khác /thamgia → cầm ⭕, hoặc chọn /choibot kho.\n"
                "3. /chono 5 → đánh ô giữa; X luôn đi trước.\n\n"
                + create_message_stage([""] * 9) +
                "\n\nBot: de • ngẫu nhiên; vua • đôi lúc sai; kho • tối ưu.\n"
                "Hai người chơi trong cùng chat. Ván hết hạn sau 15 phút không có nước đi hoặc người vào.\n"
                "Trong nhóm: mention hoặc reply bot khi gửi lệnh.",
                "/banco • Xem ván\n/dauhang • Nhận thua\n/choilai • Tái đấu có đồng ý\n"
                "/dungcaro • Đóng phòng chờ/kết thúc\n/diemcaro • Bảng điểm")
