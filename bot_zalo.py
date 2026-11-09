"""Zalo Bot adapter using the SDK's asynchronous, single-update polling API."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
import inspect
import logging
import os
from pathlib import Path
import re
import time
import unicodedata

from dotenv import load_dotenv
from zalo_bot import Bot
from zalo_bot.error import (BadRequest, Conflict, Forbidden, InvalidToken,
                            NetworkError, RetryAfter, ZaloError)

import access
import core
import storage
from zalo_games import GameContext, load_games
from zalo_ui import card
from paths import PROJECT_ROOT


load_dotenv(PROJECT_ROOT / ".env")
LOG = logging.getLogger(__name__)
MESSAGE_LIMIT = 1850
SESSION_SECONDS = 15 * 60
DEDUPE_SECONDS = 10 * 60
MAX_SESSIONS = 1000
MAX_SEEN = 10000

HELP = ("1. CHỌN BÀI\n/problems: danh sách bài theo chuyên đề\n/show <tên>: xem đề\n\n"
        "2. CHẠY THỬ\n/input <dữ liệu>: lưu input\n/run <code>: chạy C++ với input đã lưu\n\n"
        "3. NỘP BÀI\n/submit <tên> <code>: chấm bài\n\n"
        "Code dài trong chat riêng: gửi /run hoặc /submit <tên>, gửi từng phần code, "
        "rồi /done. /cancel để hủy; hết hạn sau 15 phút.\n\n"
        "Ví dụ: /show tong_hai_so\n/id: xem ID của bạn\n/admin_guide: hướng dẫn quản trị")
ADMIN_HELP = ("Lệnh quản trị (cần ZALO_ADMIN_IDS):\n"
              "/create <tên>\n/question <tên> <nội dung>\n"
              "/solution <tên> <code>\n/gen <tên> <code>\n"
              "/checker <tên> <code>\n/category <tên> <chuyên đề>\n"
              "/how solution|gentest|checker")
FIELD_COMMANDS = {"question": "question", "solution": "solution",
                  "gen": "gen_test", "checker": "checker"}
ADMIN_COMMANDS = {"create", "category", "admin_guide", "how", *FIELD_COMMANDS}
BUILTIN_COMMANDS = {"start", "help", "guide", "id", "problems", "show", "input", "photo",
                    "run", "submit", "done", "cancel", "games", *ADMIN_COMMANDS}


@dataclass
class CodeSession:
    kind: str
    problem: str = ""
    parts: list[str] = field(default_factory=list)
    size: int = 0
    expires: float = 0.0


def split_message(value: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Split plain text without dropping line endings or Unicode code points."""
    if limit < 2:
        raise ValueError("limit must be at least 2")
    chunks = []
    while value:
        if len(value) <= limit:
            chunks.append(value)
            break
        cut = value.rfind("\n", 1, limit + 1)
        if cut >= 0:
            cut += 1
        else:
            cut = limit
            while cut > 1 and (unicodedata.combining(value[cut]) or
                               value[cut] in "\ufe0e\ufe0f" or value[cut - 1] == "\u200d"):
                cut -= 1
        chunks.append(value[:cut])
        value = value[cut:]
    return chunks


def parse_command(text: str) -> tuple[str, str]:
    match = re.match(r"^/([A-Za-z_][A-Za-z_0-9]*)(?:[ \t\r\n]+([\s\S]*))?$", text)
    return (match.group(1).lower(), match.group(2) or "") if match else ("", "")


def split_name_content(value: str) -> tuple[str, str]:
    match = re.match(r"^\s*(\S+)(?:[ \t\r\n]+([\s\S]*))?$", value)
    return (match.group(1), match.group(2) or "") if match else ("", "")


def preview(value: str, limit: int = 3000) -> str:
    return value if len(value) <= limit else value[:limit] + "\n...[đã rút gọn]"


def _result_body(event: dict, name: str = "") -> str:
    kind = event.get("t")
    if kind == "not_found":
        return f"Không tìm thấy bài {name} hoặc bạn chưa có quyền xem bài."
    if kind == "ac":
        count = event.get("count")
        return f"Accepted (AC): bài {name} đã qua {count} test." if count is not None else f"Accepted (AC): bài {name} đã đạt."
    if kind == "wa":
        return (f"Wrong Answer (WA) ở test {event.get('test', '?')}.\n"
                f"Input:\n{preview(event.get('inp', '(không có)'))}\n"
                f"Output mong đợi:\n{preview(event.get('sol', '(không có)'))}\n"
                f"Output của bạn:\n{preview(event.get('out', '(không có)'))}")
    if kind == "ce":
        who = {"user": "code của bạn", "solution": "solution",
               "gen": "generator", "checker": "checker"}.get(event.get("who"), "code")
        return f"Compilation Error (CE) ở {who}:\n{event.get('stderr', '')[:5000]}"
    if kind == "rte":
        return f"Runtime Error (RTE) ở test {event.get('test', '?')}.\n{event.get('stderr', '')[:3000]}"
    if kind == "tle":
        suffix = f" ở test {event['test']}" if "test" in event else ""
        return f"Time Limit Exceeded (TLE){suffix}."
    if kind == "sys":
        messages = {
            "gen_tle": "Generator chạy quá thời gian.",
            "gen_rte": "Generator bị lỗi khi chạy.",
            "gen_empty": "Generator tạo input rỗng.",
            "gen_missing": "Bài chưa đủ test cố định và chưa có generator.",
            "sol_tle": "Solution chuẩn chạy quá thời gian.",
            "sol_rte": "Solution chuẩn bị lỗi khi chạy.",
            "no_compiler": "Máy chấm chưa có trình biên dịch g++.",
            "sandbox": "Môi trường chạy C++ chưa sẵn sàng.",
            "busy": "Máy chấm đang bận. Vui lòng thử lại.",
            "code_limit": "Code hoặc input rỗng/quá giới hạn 64 KiB.",
        }
        detail = event.get("detail", "")[:2000]
        return "Lỗi hệ thống: " + messages.get(event.get("msg"), "Không xác định.") + (f"\n{detail}" if detail else "")
    if kind == "ok":
        return "Kết quả chạy thử:\n" + event.get("output", "") + ("\n(Output đã được rút gọn.)" if event.get("truncated") else "")
    if kind == "empty":
        return "Chạy xong nhưng chương trình không in output."
    return "Lỗi hệ thống: trạng thái chấm không xác định."


def format_result(event: dict, name: str = "") -> str:
    titles = {"ac": "✅ Bài làm đã được chấp nhận", "wa": "❌ Kết quả chưa chính xác", "ce": "🛠 Cần sửa lỗi biên dịch",
              "tle": "⏱ Chương trình chạy quá thời gian", "rte": "⚠️ Chương trình gặp lỗi", "ok": "▶ Kết quả chạy thử",
              "empty": "▶ Kết quả chạy thử"}
    return card(titles.get(event.get("t"), "⚠️ Chưa thể hoàn tất"), _result_body(event, name),
                "/help cpp • Hướng dẫn chạy và nộp bài")


class ZaloAdapter:
    def __init__(self, bot: Bot, bot_id: str = "", group_enabled: bool = False,
                 games_root: Path | None = None):
        self.bot = bot
        self.bot_id = str(bot_id)
        self.group_enabled = group_enabled
        self.sessions: dict[tuple[str, str], CodeSession] = {}
        self.seen: OrderedDict[tuple[str, str], float] = OrderedDict()
        self.games = load_games(games_root or Path(__file__).resolve().parent, BUILTIN_COMMANDS)
        self.game_states: dict[tuple[str, str], dict] = {}

    def help_text(self, topic: str = "") -> str:
        topic = topic.strip().lower().removeprefix("zalo.").removeprefix("/")
        grouped = {}
        for entry in self.games.values():
            grouped.setdefault(entry.game, entry)
        if topic in ("cpp", "judge"):
            return card("📚 Cùng luyện C++", HELP)
        for game, entry in grouped.items():
            if topic == game[5:] or (topic in self.games and self.games[topic].game == game):
                commands = "\n".join(f"/{name}: {item.description}" for name, item in self.games.items()
                                     if item.game == game)
                return card(f"🎮 {entry.title}",
                            (entry.help + "\n\n" if entry.help else "") + commands,
                            "/games • Chọn game khác")
        if topic and topic != "games":
            return card("🔎 Bạn muốn tìm hướng dẫn nào?", f"Chưa có mục '{topic}'.",
                        "Gửi /help hoặc /games để xem các mục.")
        games = "\n".join(f"• {entry.title} → /help {game[5:]}" for game, entry in grouped.items())
        return card("🎮 Hôm nay chơi gì?" if topic == "games" else "👋 Chào bạn, mình là MagOJ",
                    ("Chọn trò chơi:\n" + (games or "Chưa có game được nạp.")) if topic == "games" else
                    "🎮 Giải trí → /games\n📚 Học & nộp C++ → /help cpp\n🖼 /photo <Markdown> → tạo ảnh\n\n" + games,
                    "/id • ID tài khoản\n/admin_guide • Quản trị" if topic != "games" else
                    "Gửi lệnh trên một dòng. Trong nhóm, hãy mention hoặc reply bot.")

    async def send(self, chat_id: str, text: str) -> None:
        for chunk in split_message(text or " "):
            await self.bot.send_message(chat_id=str(chat_id), text=chunk)

    async def send_photo(self, chat_id: str, markdown: str, **kwargs):
        """Reusable image reply for Zalo commands and future tasks."""
        return await core.send_markdown_photo(self.bot, chat_id, markdown, **kwargs)

    def _prune(self, now: float) -> None:
        self.sessions = {key: value for key, value in self.sessions.items()
                         if value.expires > now}
        while self.seen and now - next(iter(self.seen.values())) >= DEDUPE_SECONDS:
            self.seen.popitem(last=False)

    async def handle_update(self, update) -> None:
        if update is None:
            return
        event_name = (getattr(update, "api_kwargs", None) or {}).get("event_name")
        if event_name != "message.text.received":
            LOG.debug("Zalo: bỏ qua event %s", event_name)
            return
        message = getattr(update, "message", None)
        user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        if not message or not user or not chat or not isinstance(message.text, str):
            return
        user_id, chat_id = str(user.id), str(chat.id)
        if not user_id or not chat_id or user.is_bot or user_id == self.bot_id:
            return
        group = str(chat.type).upper() == "GROUP"
        if str(chat.type).upper() not in ("PRIVATE", "GROUP") or (group and not self.group_enabled):
            return
        now = time.monotonic()
        self._prune(now)
        message_id = getattr(message, "message_id", None)
        dedupe_key = (chat_id, str(message_id))
        if message_id and dedupe_key in self.seen:
            return
        if message_id:
            self.seen[dedupe_key] = now
            if len(self.seen) > MAX_SEEN:
                self.seen.popitem(last=False)
        display_name = getattr(user, "display_name", None) or getattr(user, "account_name", None) or ""
        await self.handle_text(chat_id, user_id, message.text, group=group, now=now,
                               display_name=display_name)

    async def handle_text(self, chat_id: str, user_id: str, text: str,
                          *, group: bool = False, now: float | None = None,
                          display_name: str = "") -> None:
        now = time.monotonic() if now is None else now
        key = (chat_id, user_id)
        session = self.sessions.get(key)
        if session and session.expires <= now:
            self.sessions.pop(key, None)
            session = None
            await self.send(chat_id, "Phiên nhập code đã hết hạn. Bắt đầu lại bằng /run hoặc /submit <tên>.")
        command, args = parse_command(text)
        if session:
            if command == "cancel" and not args:
                self.sessions.pop(key, None)
                await self.send(chat_id, "Đã hủy phiên nhập code.")
                return
            if command == "done" and not args:
                self.sessions.pop(key, None)
                code = core.strip_fences("\n".join(session.parts))
                if not access.valid_code(code):
                    await self.send(chat_id, "Code phải có nội dung và không vượt quá 64 KiB.")
                    return
                await self._execute(chat_id, user_id, session.kind, session.problem, code)
                return
            addition = len(text.encode("utf-8")) + (1 if session.parts else 0)
            if session.size + addition > access.MAX_CODE_BYTES:
                self.sessions.pop(key, None)
                await self.send(chat_id, "Code vượt quá 64 KiB; phiên đã hủy.")
                return
            session.parts.append(text)
            session.size += addition
            session.expires = now + SESSION_SECONDS
            return
        if not command:
            return
        if command in ADMIN_COMMANDS and not access.admin_id("zalo", user_id):
            await self.send(chat_id, "Lệnh này chỉ dành cho quản trị viên đã khai báo trong ZALO_ADMIN_IDS.")
            return
        if command == "start":
            await self.send(chat_id, self.help_text())
        elif command in ("help", "guide"):
            await self.send(chat_id, self.help_text(args))
        elif command == "games":
            await self.send(chat_id, self.help_text("games"))
        elif command == "photo":
            if not args.strip():
                await self.send(chat_id, "Dùng /photo <Markdown> để gửi nội dung thành ảnh PNG.")
                return
            try:
                await self.send_photo(chat_id, args)
            except (ValueError, core.PhotoRenderError) as exc:
                await self.send(chat_id, str(exc))
            except (OSError, ZaloError):
                LOG.warning("Zalo: không lưu hoặc gửi được ảnh PNG")
                await self.send(chat_id, "Chưa gửi được ảnh. Vui lòng thử lại sau.")
        elif command == "id":
            await self.send(chat_id, f"Zalo user ID của bạn: {user_id}")
        elif command == "admin_guide":
            await self.send(chat_id, card("🛠 Góc quản trị", ADMIN_HELP))
        elif command == "how":
            topic = args.strip().lower()
            samples = {"solution": ("Solution đọc stdin và in stdout. Ví dụ:\n" + core.SAMPLE_SOLUTION),
                       "sol": ("Solution đọc stdin và in stdout. Ví dụ:\n" + core.SAMPLE_SOLUTION),
                       "gen": ("Generator tự sinh input và in stdout; MAGOJ_SEED giúp tái tạo test. Ví dụ:\n" + core.SAMPLE_GEN),
                       "gentest": ("Generator tự sinh input và in stdout; MAGOJ_SEED giúp tái tạo test. Ví dụ:\n" + core.SAMPLE_GEN),
                       "checker": ("Checker nhận input, ENDINP, output chuẩn, ENDOUT, output người nộp; in AC nếu đúng. Ví dụ:\n" + core.SAMPLE_CHECKER)}
            await self.send(chat_id, samples.get(topic, "Chọn /how solution, /how gentest hoặc /how checker."))
        elif command == "problems":
            categories = core.list_visible_problems("zalo", user_id)
            body = "\n".join(f"{category}:\n" + "\n".join(f"  {name}" for name in names)
                             for category, names in categories.items())
            await self.send(chat_id, card("📚 Chọn một bài để bắt đầu", body or "Chưa có bài tập được công bố.",
                                          "Xem đề: /show <tên bài>"))
        elif command == "show":
            name = args.strip()
            problem = core.visible_problem(name, "zalo", user_id) if name else None
            if problem:
                await self.send(chat_id, card(f"📄 {name}", f"Chuyên đề: {problem.get('category', 'Chưa phân loại')}\n"
                                f"Giới hạn: {problem.get('time_limit', core.TIMEOUT)} giây, "
                                f"{problem.get('memory_limit', 128)} MiB\n\n{problem.get('question', '')}",
                                f"Nộp bài: /submit {name} <code C++>"))
            else:
                await self.send(chat_id, "Dùng /show <tên bài>. Bài cần tồn tại và đã được công bố.")
        elif command == "input":
            if not access.valid_input(args):
                await self.send(chat_id, "Input vượt quá 64 KiB.")
            else:
                core.set_user_input(f"zalo:{user_id}", args)
                await self.send(chat_id, "Đã lưu input chạy thử.")
        elif command in ("run", "submit"):
            name, code = split_name_content(args) if command == "submit" else ("", args)
            if command == "submit" and not name:
                await self.send(chat_id, "Cú pháp: /submit <tên bài> <code C++> hoặc /submit <tên bài> rồi gửi code và /done.")
                return
            if not code.strip():
                if group:
                    await self.send(chat_id, "Vui lòng dùng chat riêng để gửi code nhiều phần; nhóm chỉ nhận tin nhắn mention/reply.")
                elif len(self.sessions) >= MAX_SESSIONS:
                    await self.send(chat_id, "Đang có quá nhiều phiên nhập code. Vui lòng thử lại sau.")
                else:
                    self.sessions[key] = CodeSession(command, name, expires=now + SESSION_SECONDS)
                    await self.send(chat_id, card("📝 Gửi code của bạn nhé", "Gửi từng phần code theo đúng thứ tự.\nPhiên có hạn 15 phút, tối đa 64 KiB.",
                                                  "/done • Gửi đi\n/cancel • Hủy nhập code"))
                return
            code = core.strip_fences(code)
            if not access.valid_code(code):
                await self.send(chat_id, "Code phải có nội dung và không vượt quá 64 KiB.")
                return
            await self._execute(chat_id, user_id, command, name, code)
        elif command == "cancel":
            await self.send(chat_id, "Không có phiên nhập code đang hoạt động.")
        elif command == "done":
            await self.send(chat_id, "Không có phiên nhập code đang hoạt động.")
        elif command == "create":
            name = args.strip()
            if not name:
                await self.send(chat_id, "Cú pháp: /create <tên bài>.")
            elif core.create_problem(name, user_id):
                storage.record_admin_event("zalo", user_id, "create", name)
                await self.send(chat_id, f"Đã tạo bài {name}.")
            else:
                await self.send(chat_id, f"Bài {name} đã tồn tại.")
        elif command in FIELD_COMMANDS or command == "category":
            name, content = split_name_content(args)
            if not name or not content.strip():
                await self.send(chat_id, f"Cú pháp: /{command} <tên bài> <nội dung>.")
                return
            if command == "category":
                changed = core.set_category(name, content.strip())
            else:
                value = core.strip_fences(content) if command != "question" else content
                if command != "question" and not access.valid_code(value):
                    await self.send(chat_id, "Code phải có nội dung và không vượt quá 64 KiB.")
                    return
                changed = core.set_problem_field(name, FIELD_COMMANDS[command], value)
            if changed:
                storage.record_admin_event("zalo", user_id, command, name)
            await self.send(chat_id, f"Đã cập nhật {command} cho {name}." if changed else f"Không tìm thấy bài {name}.")
        elif command in self.games:
            entry = self.games[command]
            state = self.game_states.setdefault((entry.game, chat_id), {})
            # Keep names on one line so profile text cannot break message layouts.
            name = " ".join(display_name.split())[:100] if isinstance(display_name, str) else ""
            context = GameContext(chat_id, user_id, args, state, self.send, name)
            try:
                result = entry.handler(context)
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, str) and result:
                    await self.send(chat_id, result)
            except Exception:
                LOG.exception("Lệnh game Zalo /%s bị lỗi", command)
                await self.send(chat_id, card("⚠️ Game đang gián đoạn", "Chưa xử lý được lệnh này. Bạn thử lại sau nhé.",
                                              f"Xem hướng dẫn: /help {entry.game[5:]}"))
        else:
            await self.send(chat_id, card("🔎 Mình chưa nhận ra lệnh này", f"/{command} chưa được hỗ trợ.",
                                          "/help • Menu chính\n/games • Danh sách game"))

    async def _execute(self, chat_id: str, user_id: str, kind: str,
                       name: str, code: str) -> None:
        if kind == "run":
            await self.send(chat_id, card("⏳ Đang chạy thử…", "Mình đang biên dịch C++ với input bạn đã lưu."))
            result = await core.run_once(code, core.get_user_input(f"zalo:{user_id}"))
            await self.send(chat_id, format_result(result))
            return
        await self.send(chat_id, card("⏳ Đang chấm bài…", f"Bài: {name}\nKết quả sẽ được gửi khi chấm xong."))
        async for event in core.judge(name, code, "zalo", user_id):
            if event.get("t") != "status":
                await self.send(chat_id, format_result(event, name))


async def run_zalo_bot(token: str | None = None) -> None:
    token = token or os.getenv("ZALO_BOT_TOKEN", "").strip()
    if not token:
        return
    delay = 1.0
    while True:
        try:
            async with Bot(token) as bot:
                me = await bot.get_me()
                adapter = ZaloAdapter(bot, str(me.id), bool(getattr(me, "can_join_groups", False)))
                LOG.info("Zalo bot đã kết nối; polling bắt đầu")
                delay = 1.0
                while True:
                    try:
                        update = await asyncio.wait_for(bot.get_update(timeout=25, read_timeout=5), timeout=35)
                        if update is not None:
                            await adapter.handle_update(update)
                        delay = 1.0
                    except (NetworkError, asyncio.TimeoutError, OSError) as exc:
                        LOG.warning("Zalo polling lỗi mạng (%s); thử lại sau %.0f giây", type(exc).__name__, delay)
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 30.0)
                    except RetryAfter as exc:
                        await asyncio.sleep(min(max(exc.retry_after, 1), 60))
                    except (KeyError, TypeError, ValueError) as exc:
                        LOG.warning("Zalo update không hợp lệ (%s)", type(exc).__name__)
                        await asyncio.sleep(1)
        except InvalidToken:
            LOG.error("Zalo dừng: ZALO_BOT_TOKEN không hợp lệ")
            return
        except (Forbidden, Conflict, BadRequest) as exc:
            LOG.error("Zalo dừng: polling bị từ chối (%s); kiểm tra quyền và webhook hiện có", type(exc).__name__)
            return
        except (NetworkError, asyncio.TimeoutError, OSError) as exc:
            LOG.warning("Zalo không kết nối được (%s); thử lại sau %.0f giây", type(exc).__name__, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
        except RetryAfter as exc:
            await asyncio.sleep(min(max(exc.retry_after, 1), 60))
        except ZaloError as exc:
            LOG.error("Zalo dừng: lỗi SDK (%s)", type(exc).__name__)
            return
