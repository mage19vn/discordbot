import asyncio
import hashlib
import html
import json
import os
import random
import re
import urllib.parse

import httpx
from dotenv import load_dotenv
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                       ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, WebAppInfo)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)
from telegram.request import HTTPXRequest

import core
import access
import problem_import
import storage

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
NOTIFY_CHAT_ID = os.getenv("TELEGRAM_NOTIFY_CHAT_ID")
WEBAPP_URL = os.getenv("MAGOJ_WEBAPP_URL", "").rstrip("/")  # vd: https://magoj-submit.vercel.app
PROXY = os.getenv("TELEGRAM_PROXY", "").strip()

CHUNK = 4000

MESSAGE_REPLY_TEMPLATES = {
    "ac": [
        "Chúc mừng! Bạn đã giải đúng bài toán.",
        "AC rồi! Code mượt như nhung, các test cases đều vượt qua! 🎉",
        "Tuyệt vời! Bài này đã bị bạn chinh phục hoàn toàn!",
        "Full AC! Hôm nay bạn chính là main character! ⭐",
        "Đỉnh quá! Máy chấm cũng phải gật gù công nhận!",
        "Chính xác 100%! Cứ đà này thì ICPC không còn xa đâu! 🚀",
    ],
    "wa": [
        "Sai rồi, thử lại nhé!",
        "Suýt nữa thì đúng rồi! Soi kỹ output từng test xem nào 🔍",
        "WA rồi... bug đang trốn ở đâu đó, lôi nó ra ánh sáng đi!",
        "Chưa đúng nè, nhưng đừng nản — cao thủ cũng từng WA cả trăm lần!",
        "Sai một ly... kiểm tra lại biên (edge case) xem sao?",
        "Gần đúng rồi đó! In output ra giấy so tay thử xem 👀",
    ],
    "tle": [
        "Chạy quá lâu, thử tối ưu code hoặc kiểm tra lại.",
        "TLE! Code bạn chạy marathon còn test thì chạy nước rút 🏃",
        "Quá giờ rồi! Có vòng lặp nào đang chạy vô tận không?",
        "Chậm quá bạn ơi — thử nghĩ thuật toán O(n log n) xem sao?",
        "Time out! Độ phức tạp đang hơi 'cồng kềnh' đó, gọt bớt đi nào ✂️",
        "2 giây trôi qua như 2 năm... tối ưu lại code nhé!",
    ],
    "rte": [
        "Chạy bị lỗi, kiểm tra lại code nhé!",
        "RTE! Chương trình crash giữa chừng — mảng có bị tràn index không? 💥",
        "Lỗi runtime rồi! Chia cho 0 hay truy cập null ở đâu đó?",
        "Code sập nguồn giữa đường... kiểm tra lại con trỏ và mảng nhé!",
        "Crash! Thử chạy tay với test nhỏ để bắt bug nào 🐞",
        "Runtime Error — máy chấm cũng sốc! Coi lại phần đọc input nha!",
    ],
    "ce": [
        "Code biên dịch lỗi, kiểm tra lại code nhé!",
        "CE! Trình biên dịch không hiểu bạn đang viết gì... thiếu `;` ở đâu không? 😅",
        "Biên dịch thất bại! Thiếu `#include` hay sai tên biến nào đó?",
        "Compile Error — code chưa qua được cửa ải đầu tiên, sửa rồi nộp lại nhé!",
        "Lỗi biên dịch kìa! Đọc kỹ thông báo lỗi, nó đang mách bạn đó 💡",
        "g++ lắc đầu ngán ngẩm... kiểm tra lại cú pháp nhé bạn!",
    ],
}


def create_app():
    builder = ApplicationBuilder().token(TOKEN)
    builder = builder.request(HTTPXRequest(
        proxy=PROXY or None,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    ))
    return builder.post_init(post_init).build()


def pre(code: str) -> str:
    return "<pre>" + html.escape(code) + "</pre>"


def pre_limited(code: str, max_escaped: int = 1200) -> str:
    parts, size = [], 0
    for char in code:
        escaped = html.escape(char)
        if size + len(escaped) > max_escaped:
            break
        parts.append(escaped)
        size += len(escaped)
    return "<pre>" + "".join(parts) + "</pre>"


async def reply_long(message, text: str):
    while len(text) > CHUNK:
        cut = text.rfind("\n", 0, CHUNK)
        if cut <= 0:
            cut = CHUNK
        await message.reply_text(text[:cut], parse_mode=ParseMode.HTML)
        text = text[cut:]
    if text:
        await message.reply_text(text, parse_mode=ParseMode.HTML)


def cmd_args(text: str):
    parts = text.strip().split(None, 2)
    return parts[0].split("@")[0], parts[1:]


def err_not_found(name: str) -> str:
    return f"❌ <b>Lỗi:</b> Không tìm thấy bài <code>{html.escape(name)}</code>."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = 20
    msg = await update.message.reply_text(
        "🤖 <b>Đang khởi động...</b>",
        parse_mode=ParseMode.HTML,
    )
    for i in range(1, total + 1):
        pct = i / total * 100
        bar = "█" * (i * 2) + "░" * ((total - i) * 2)
        await msg.edit_text(
            f"🤖 <b>Đang khởi động...</b>\n<pre>[{bar}] {pct:.1f}%</pre>",
            parse_mode=ParseMode.HTML,
        )
        await asyncio.sleep(0.15)

    await msg.edit_text(
            f"🤖 <b>Đã khởi động: </b>\n<pre>MAGoj by Mage.</pre>",
            parse_mode=ParseMode.HTML,
        )

    await asyncio.sleep(1)

    await msg.edit_text(
        "🤖 <b>Bot chấm bài đã sẵn sàng!</b>\n"
        "Gõ /guide để xem hướng dẫn cho học sinh,\n"
        "/admin_guide để xem hướng dẫn cho giáo viên.",
        parse_mode=ParseMode.HTML,
    )


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, args = cmd_args(update.message.text)
    code = core.strip_fences(" ".join(args))
    print(f'Code: "\n{code}"')
    await update.message.reply_text(
        f"💬 <b>Đang xử lý đoạn hội thoại:</b>\n{pre(code)}",
        parse_mode=ParseMode.HTML,
    )


async def haogay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open("haogay.png", "rb") as f:
            await update.message.reply_photo(photo=f)
    except FileNotFoundError:
        await update.message.reply_text(
            "❌ Mình không tìm thấy file <code>haogay.png</code>. "
            "Bạn nhớ lưu ảnh vào cùng thư mục với code nhé!",
            parse_mode=ParseMode.HTML,
        )


async def _require_admin(update):
    if access.telegram_admin(update.effective_user):
        return True
    await update.effective_message.reply_text("⛔ Lệnh này chỉ dành cho quản trị viên.")
    return False


async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    _, args = cmd_args(update.message.text)
    name = " ".join(args).strip()
    if not name:
        await update.message.reply_text("❌ Cú pháp: <code>/create tên_bài</code>", parse_mode=ParseMode.HTML)
        return
    if core.create_problem(name, update.effective_user.id):
        storage.record_admin_event("telegram", update.effective_user.id, "create", name)
        text = f"✅ <b>Thành công:</b> Đã tạo bài <code>{html.escape(name)}</code>."
    else:
        text = f"❌ <b>Lỗi:</b> Có bài tên <code>{html.escape(name)}</code> rồi nhen."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def _set_field(update, field: str, label: str):
    if not await _require_admin(update):
        return
    _, args = cmd_args(update.message.text)
    if len(args) < 2:
        await update.message.reply_text(
            f"❌ Cú pháp: <code>/{label} tên_bài</code> + code trong khối ```",
            parse_mode=ParseMode.HTML,
        )
        return
    name, code = args[0].strip(), core.strip_fences(args[1])
    if core.set_problem_field(name, field, code):
        storage.record_admin_event("telegram", update.effective_user.id, field, name)
        text = f"✅ <b>Thành công:</b> Đã cập nhật {label} cho bài <code>{html.escape(name)}</code>."
    else:
        text = err_not_found(name)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def solution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_field(update, "solution", "Code Giải (Solution)")


async def gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_field(update, "gen_test", "Code Sinh Test (Generator)")


async def question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_field(update, "question", "Đề Bài")


async def checker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_field(update, "checker", "Code Checker")

_SUB_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_SUB_LETTERS = {"i": "ᵢ", "j": "ⱼ", "k": "ₖ", "n": "ₙ", "m": "ₘ"}
_SUP_CHARS = str.maketrans("0123456789+-()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿⁱ")


def _prettify_math(text: str) -> str:
    """Đổi ký hiệu toán học kiểu code thành ký tự Unicode đẹp:
    <= -> ≤, p_1 -> p₁, 10^9 -> 10⁹, ... -> …
    Chạy lúc code dạng khối ``` đã được tách ra placeholder nên không đụng tới code khối.
    Code inline `...` cũng được làm đẹp (vì trong đề bài thường là công thức toán).
    Nhận cả text thô lẫn text đã escape HTML."""
    text = text.replace("&lt;=", "≤").replace("<=", "≤")
    text = text.replace("&gt;=", "≥").replace(">=", "≥")
    text = text.replace("=&gt;", "⇒").replace("=>", "⇒")
    text = text.replace("!=", "≠")
    text = re.sub(r"(?<!\.)\.\.\.(?!\.)", "…", text)
    # p_1 -> p₁, a_12 -> a₁₂
    text = re.sub(r"([A-Za-z])_(\d+)",
                  lambda m: m.group(1) + m.group(2).translate(_SUB_DIGITS), text)
    # p_i -> pᵢ (chỉ các chữ chỉ số hay gặp)
    text = re.sub(r"([A-Za-z])_([ijknm])\b",
                  lambda m: m.group(1) + _SUB_LETTERS[m.group(2)], text)
    # 10^9 -> 10⁹, x^n -> xⁿ, 2^(n+1) -> 2⁽ⁿ⁺¹⁾
    text = re.sub(r"\^(\([^()]*\)|[0-9+\-ni]+)",
                  lambda m: m.group(1).translate(_SUP_CHARS), text)
    return text


def default_question(ques: str) -> str:
    """Chuẩn hóa đề bài từ markdown (kiểu Discord) sang HTML (Telegram)."""
    blocks, codes = [], []

    def _save_block(m):
        blocks.append(m.group(1).strip("\n"))
        return f"\x00B{len(blocks) - 1}\x00"

    def _save_code(m):
        codes.append(m.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    text = re.sub(r"```(?:\w*\n)?(.*?)```", _save_block, ques, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+)`", _save_code, text)
    text = html.escape(text)

    def _heading(m):
        inner = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(1))
        inner = re.sub(r"\*([^*]+?)\*", r"\1", inner)
        return f"<b>{inner}</b>"

    text = re.sub(r"(?m)^#{1,6}\s*(.+)$", _heading, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text, flags=re.DOTALL)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s*-\s+", "• ", text)
    text = _prettify_math(text)

    for i, b in enumerate(blocks):
        text = text.replace(f"\x00B{i}\x00", "<pre>" + html.escape(b) + "</pre>")
    for i, c in enumerate(codes):
        text = text.replace(f"\x00C{i}\x00",
                            "<code>" + _prettify_math(html.escape(c)) + "</code>")
    return text


def _html_chunks(body: str, limit: int = 3900):
    """Split rendered question HTML while balancing open tags in every message."""
    stack, parts, size = [], [], 0
    tokens = re.finditer(r"<[^>]+>|&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);|.",
                         body, flags=re.DOTALL)
    for match in tokens:
        token = match.group()
        start = re.fullmatch(r"<([a-z]+)>", token)
        end = re.fullmatch(r"</([a-z]+)>", token)
        if start:
            after = [*stack, (start.group(1), token)]
        elif end and stack and stack[-1][0] == end.group(1):
            after = stack[:-1]
        else:
            after = stack
        closing = "".join(f"</{name}>" for name, _ in reversed(after))
        if size + len(token) + len(closing) > limit and parts:
            yield "".join(parts) + "".join(f"</{name}>" for name, _ in reversed(stack))
            parts = [tag for _, tag in stack]
            size = sum(map(len, parts))
        parts.append(token)
        size += len(token)
        stack = after
    if parts:
        yield "".join(parts) + "".join(f"</{name}>" for name, _ in reversed(stack))


TELEGRAPH_API = "https://api.telegra.ph"
# Tăng số này mỗi khi đổi cách render trang -> các trang cũ tự tạo lại
TELEGRAPH_RENDER_VERSION = 4


async def _telegraph(method: str, payload: dict):
    async with httpx.AsyncClient(timeout=15.0, proxy=PROXY or None) as client:
        r = await client.post(f"{TELEGRAPH_API}/{method}", json=payload)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(str(data.get("error")))
        return data["result"]


async def _telegraph_token() -> str:
    path = "telegraph_token.txt"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            token = f.read().strip()
        if token:
            return token
    res = await _telegraph("createAccount", {"short_name": "MagOJ", "author_name": "MagOJ"})
    token = res["access_token"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(token)
    return token


def _inline_nodes(s: str):
    nodes, pos = [], 0
    tag_map = {"b": "strong", "i": "em", "code": "code"}
    for m in re.finditer(r"<(b|i|code)>(.*?)</\1>", s, flags=re.DOTALL):
        if m.start() > pos:
            t = html.unescape(s[pos:m.start()])
            if t:
                nodes.append(t)
        inner = html.unescape(m.group(2))
        if inner:
            nodes.append({"tag": tag_map[m.group(1)], "children": [inner]})
        pos = m.end()
    tail = html.unescape(s[pos:])
    if tail:
        nodes.append(tail)
    return nodes


# Bảng emoji gắn theo từ khóa trong tiêu đề mục — tự thêm/sửa thoải mái
SECTION_EMOJI = [
    ("input", "📥"), ("output", "📤"),
    ("ví dụ", "💡"), ("example", "💡"),
    ("giới hạn", "⏱️"), ("limit", "⏱️"),
    ("chú thích", "📌"), ("note", "📌"),
    ("ràng buộc", "📏"), ("constraint", "📏"),
]


def _section_emoji(text: str) -> str:
    low = text.lower()
    return "".join(e for k, e in SECTION_EMOJI if k in low)


def question_to_nodes(ques_md: str):
    """Chuyển đề markdown thành nodes Telegraph: tiêu đề mục -> h4 + emoji,
    dòng giới hạn -> blockquote, gạch đầu dòng -> ul, khối code -> pre."""
    html_text = default_question(ques_md)
    nodes = []
    buf, ul_buf = [], []

    def flush_p():
        if buf:
            children = []
            for li, ln in enumerate(buf):
                if li:
                    children.append({"tag": "br"})
                children.extend(_inline_nodes(ln))
            nodes.append({"tag": "p", "children": children or [""]})
            buf.clear()

    def flush_ul():
        if ul_buf:
            nodes.append({"tag": "ul", "children": [
                {"tag": "li", "children": _inline_nodes(ln[2:])} for ln in ul_buf
            ]})
            ul_buf.clear()

    def handle_line(ln: str):
        ln = ln.strip()
        # Dòng chỉ gồm chữ in đậm -> tiêu đề mục (h3) + emoji
        solo = re.fullmatch(r"<b>(.*?)</b>", ln, flags=re.DOTALL)
        if solo:
            flush_p(); flush_ul()
            title = html.unescape(solo.group(1))
            emoji = _section_emoji(title)
            nodes.append({"tag": "h3", "children": [(emoji + " " if emoji else "") + title]})
            return
        # Dòng chỉ gồm chữ in nghiêng (vd *Giới hạn...*) -> khung trích dẫn
        solo_i = re.fullmatch(r"<i>(.*?)</i>", ln, flags=re.DOTALL)
        if solo_i:
            flush_p(); flush_ul()
            text_i = html.unescape(solo_i.group(1))
            emoji = _section_emoji(text_i)
            nodes.append({"tag": "blockquote",
                          "children": [(emoji + " " if emoji else "") + text_i]})
            return
        if ln.startswith("• "):
            flush_p()
            ul_buf.append(ln)
            return
        flush_ul()
        buf.append(ln)

    for part in re.split(r"(<pre>.*?</pre>)", html_text, flags=re.DOTALL):
        m = re.fullmatch(r"<pre>(.*?)</pre>", part, flags=re.DOTALL)
        if m:
            flush_p(); flush_ul()
            nodes.append({"tag": "pre", "children": [html.unescape(m.group(1))]})
            continue
        for para in part.split("\n\n"):
            for ln in para.split("\n"):
                if ln.strip():
                    handle_line(ln)
            flush_p(); flush_ul()
    return nodes


async def _get_telegraph_url(name: str, ques_md: str):
    p = core.get_problem(name)
    qhash = hashlib.md5(f"{TELEGRAPH_RENDER_VERSION}:{ques_md}".encode("utf-8")).hexdigest()
    if p.get("page_url") and p.get("page_hash") == qhash:
        return p["page_url"]
    try:
        token = await _telegraph_token()
        res = await _telegraph("createPage", {
            "access_token": token,
            "title": f"MagOJ - {name}",
            "author_name": "MagOJ",
            "content": question_to_nodes(ques_md),
        })
        url = res.get("url", "")
        if url:
            core.set_problem_field(name, "page_url", url)
            core.set_problem_field(name, "page_hash", qhash)
            return url
    except Exception as e:
        print(f"Telegraph failed: {type(e).__name__}: {e}")
    return None


def _cat_keyboard(cats) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📁 {c} ({len(ps)} bài)", callback_data=f"prob:cat:{i}")]
        for i, (c, ps) in enumerate(cats.items())
    ])


def _prob_keyboard(problems, ci: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"📝 {p}", callback_data=f"prob:show:{ci}:{pi}")]
        for pi, p in enumerate(problems)
    ]
    rows.append([InlineKeyboardButton("⬅️ Chuyên đề khác", callback_data="prob:list")])
    return InlineKeyboardMarkup(rows)


async def _deliver_problem(send, name: str, user_id=None):
    """Hàm show duy nhất — cả lệnh /show và nút bấm /problems đều gọi hàm này.
    send là hàm async dạng send(text, parse_mode=..., reply_markup=...)."""
    p = core.visible_problem(name, "telegram", user_id)
    if p is None:
        await send(err_not_found(name), parse_mode=ParseMode.HTML)
        return
    ques = default_question(p["question"]) if p["question"] else "<i>Chưa có nội dung đề bài.</i>"
    header = (f"📝 <b>Đề bài: {html.escape(name)}</b>\n"
              f"{p.get('test_count', 10)} test · {p.get('time_limit', 2)} giây/test "
              f"· {p.get('memory_limit', 128)} MiB · v{p.get('version', 1)}")
    open_tag, close_tag = "<blockquote expandable>", "</blockquote>"
    limit = 4000 - len(open_tag) - len(close_tag)
    body = ques

    rows = []
    if p["question"]:
        page_url = await _get_telegraph_url(name, p["question"])
        if page_url:
            rows.append([InlineKeyboardButton("📖 Mở ở tab mới", url=page_url)])
    if WEBAPP_URL:
        # Nút inline chỉ để mở bước tiếp theo: Web App CHỈ gửi được data về
        # (sendData) khi mở từ nút keyboard, không phải nút inline.
        cb = "wasub:" + urllib.parse.quote(name, safe="")
        if len(cb.encode()) <= 64:  # giới hạn callback_data của Telegram
            rows.append([InlineKeyboardButton("📝 Nộp bài", callback_data=cb)])
    markup = InlineKeyboardMarkup(rows) if rows else None

    if len(header) + 1 + len(open_tag) + len(body) + len(close_tag) <= 4000:
        await send(f"{header}\n{open_tag}{body}{close_tag}",
                   parse_mode=ParseMode.HTML, reply_markup=markup)
        return

    await send(header, parse_mode=ParseMode.HTML, reply_markup=markup)
    for chunk in _html_chunks(body, limit):
        await send(f"{open_tag}{chunk}{close_tag}", parse_mode=ParseMode.HTML)


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, args = cmd_args(update.message.text)
    name = " ".join(args).strip()
    await _deliver_problem(update.message.reply_text, name, update.effective_user.id)


async def _safe_edit(status_msg, text, **kwargs):
    """Sửa tin nhắn trạng thái; nếu Telegram không cho sửa (vd tin nhắn trả lời
    service message của Web App) thì gửi tin mới và trả về tin mới để các lần
    cập nhật sau nhắm đúng chỗ."""
    try:
        await status_msg.edit_text(text, **kwargs)
        return status_msg
    except BadRequest as e:
        print(f"[judge] không sửa được tin nhắn chat={status_msg.chat_id} "
              f"msg={status_msg.message_id}: {e} -> gửi tin mới")
        return await status_msg.reply_text(text, **kwargs)


async def _run_judge(name: str, code: str, user, on_update):
    """Chạy core.judge và báo tiến trình qua on_update(text, parse_mode=...) —
    dùng chung cho /submit (sửa tin nhắn) và Web App (gửi tin riêng)."""
    async for ev in core.judge(name, code, "telegram", user.id):
        t = ev["t"]
        if t == "not_found":
            await on_update(err_not_found(name), parse_mode=ParseMode.HTML)
            return
        if t == "status":
            if ev["msg"] == "testing":
                await on_update(
                    f"🚀 <b>Code biên dịch thành công. Đang chạy {ev.get('count', 10)} test...</b>",
                    parse_mode=ParseMode.HTML,
                )
            continue
        if t == "ce":
            who = {"user": "Code của bạn", "solution": "Code Solution",
                   "gen": "Code Gen Test", "checker": "Code Checker"}[ev["who"]]
            title = "❌ <b>Compilation Error</b>" if ev["who"] == "user" else "⚠️ <b>Lỗi hệ thống</b>"
            await on_update(
                f"{title}\n<b>{who} bị lỗi biên dịch:</b>\n{pre_limited(ev['stderr'], 2500)}",
                parse_mode=ParseMode.HTML,
            )
            return
        if t == "sys":
            msgs = {
                "gen_tle": f"❌ <b>Lỗi hệ thống:</b> TLE khi sinh test (Generator bị lặp vô hạn).",
                "gen_rte": f"❌ <b>Lỗi hệ thống:</b> Trình sinh test (Gen) gặp lỗi (RTE).\n{pre(ev.get('detail', '')[:1000])}",
                "gen_empty": f"⚠️ <b>Cảnh báo:</b> Trình sinh test (Gen) tạo ra input rỗng.",
                "sol_tle": f"❌ <b>Lỗi hệ thống:</b> TLE ở code Solution chuẩn.",
                "sol_rte": f"❌ <b>Lỗi hệ thống:</b> Code Solution chuẩn gặp lỗi (RTE).\n{pre(ev.get('detail', '')[:1000])}",
                "no_compiler": f"❌ <b>Lỗi hệ thống:</b> Máy chấm chưa cài <code>g++</code>, không biên dịch được. Báo admin cài giúp nhé!",
                "gen_missing": "❌ Bài chưa có đủ test cố định và chưa có generator.",
                "sandbox": "❌ Trình chạy chấm bài chưa sẵn sàng. Báo quản trị viên kiểm tra cấu hình.",
                "busy": "⏳ Máy chấm đang bận. Vui lòng nộp lại sau.",
                "code_limit": "❌ Code phải có nội dung và không vượt quá 64 KiB.",
            }
            await on_update(msgs[ev["msg"]], parse_mode=ParseMode.HTML)
            return
        if t == "rte":
            await on_update(
                f"{random.choice(MESSAGE_REPLY_TEMPLATES['rte'])}\n"
                f"❌ <b>Runtime Error (RTE) tại Test {ev['test']}</b>\n{pre(ev['stderr'][:1800])}",
                parse_mode=ParseMode.HTML,
            )
            return
        if t == "tle":
            await on_update(
                f"{random.choice(MESSAGE_REPLY_TEMPLATES['tle'])}\n"
                f"❌ <b>Time Limit Exceeded (TLE) tại Test {ev['test']}</b> "
                f"(quá {ev.get('limit', 2)} giây).",
                parse_mode=ParseMode.HTML,
            )
            return
        if t == "wa":
            await on_update(
                f"{random.choice(MESSAGE_REPLY_TEMPLATES['wa'])}\n"
                f"❌ <b>Wrong Answer (WA) tại Test {ev['test']}</b>\n"
                f"<b>Input sinh ra:</b>\n{pre_limited(ev['inp'], 700)}\n"
                f"<b>Output mong đợi:</b>\n{pre_limited(ev['sol'], 700)}\n"
                f"<b>Output của bạn:</b>\n{pre_limited(ev['out'], 700)}\n"
                f"Seed: <code>{ev.get('seed', '')}</code> · dùng /lastfail để xem lại input.",
                parse_mode=ParseMode.HTML,
            )
            return
        if t == "ac":
            mention = f'<a href="tg://user?id={user.id}">{html.escape(user.first_name)}</a>'
            await on_update(
                f"{random.choice(MESSAGE_REPLY_TEMPLATES['ac'])}\n"
                f"✅ <b>ACCEPTED!</b>\nChúc mừng {mention}, code của bạn đã vượt qua "
                f"{ev.get('count', 10)}/{ev.get('count', 10)} test bài <code>{html.escape(name)}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, args = cmd_args(update.message.text)
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Cú pháp: <code>/submit tên_bài</code> + code trong khối ```",
            parse_mode=ParseMode.HTML,
        )
        return
    name, code = args[0].strip(), core.strip_fences(args[1])
    await _submit_code(update, update.message, name, code)


async def _submit_code(update, message, name, code):
    status_msg = await message.reply_text(
        f"⏳ <b>Đang khởi tạo môi trường chấm bài <code>{html.escape(name)}</code>...</b>",
        parse_mode=ParseMode.HTML,
    )

    async def edit_update(text, **kw):
        nonlocal status_msg
        status_msg = await _safe_edit(status_msg, text, **kw)

    await _run_judge(name, code, update.effective_user, edit_update)


async def submit_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.file_name and doc.file_name.lower().endswith(".json"):
        await importjson_document(update, context)
        return
    if not doc.file_name or not doc.file_name.lower().endswith(".cpp"):
        return
    caption = (update.message.caption or "").split()
    if len(caption) != 2 or caption[0].split("@")[0] != "/submit":
        await update.message.reply_text("Gửi file .cpp kèm chú thích: /submit tên_bài")
        return
    if doc.file_size is None or doc.file_size > access.MAX_CODE_BYTES:
        await update.message.reply_text("File .cpp phải có dung lượng tối đa 64 KiB.")
        return
    try:
        remote = await context.bot.get_file(doc.file_id)
        data = await remote.download_as_bytearray()
        if len(data) > access.MAX_CODE_BYTES:
            await update.message.reply_text("File .cpp vượt quá 64 KiB.")
            return
        code = data.decode("utf-8")
    except (UnicodeDecodeError, TelegramError):
        await update.message.reply_text("Không đọc được file .cpp UTF-8. Hãy gửi lại.")
        return
    await _submit_code(update, update.message, caption[1], code)


async def importjson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    await update.message.reply_text(
        "Gửi file .json trong chat riêng với bot, kèm caption /importjson. "
        "Mỗi bài có name, statement (title, description, input, output, "
        "constraints, examples, notes), solution và các giới hạn. "
        "Có thể dùng question Markdown kiểu cũ thay cho statement. "
        "Bài mới mặc định ở trạng thái ẩn; dùng /publish tên_bài on sau khi kiểm tra.")


async def updatejson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    await update.message.reply_text(
        "Để sửa bài đã có, gửi file .json đầy đủ trong chat riêng với bot, "
        "caption /updatejson. File cần giữ nguyên name và đủ các trường như "
        "file đã nhập. Bot giữ lịch sử nộp bài và từ chối cả file nếu có bài chưa tồn tại.")


async def importjson_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Hãy gửi file JSON trong chat riêng với bot để giữ kín solution.")
        return
    message = update.message
    caption = (message.caption or "").strip().split()
    action = caption[0].split("@")[0] if len(caption) == 1 else ""
    if action not in ("/importjson", "/updatejson"):
        await message.reply_text("Gửi file .json với caption /importjson hoặc /updatejson.")
        return
    doc = message.document
    if doc.file_size is None or doc.file_size > problem_import.MAX_JSON_BYTES:
        await message.reply_text("File JSON phải có dung lượng tối đa 256 KiB.")
        return
    try:
        remote = await context.bot.get_file(doc.file_id)
        data = await remote.download_as_bytearray()
        updating = action == "/updatejson"
        problems = problem_import.parse_problem_json(data, require_full=updating)
        if updating:
            storage.update_problems(problems, "telegram", update.effective_user.id)
        else:
            storage.import_problems(problems, "telegram", update.effective_user.id)
    except ValueError as exc:
        await message.reply_text(f"❌ Không {'cập nhật' if action == '/updatejson' else 'nhập'} bài: {exc}")
        return
    except TelegramError:
        await message.reply_text("❌ Không tải được file JSON từ Telegram. Hãy thử lại.")
        return
    names = ", ".join(name for name, _ in problems)
    if updating:
        await message.reply_text(f"✅ Đã cập nhật {len(problems)} bài: {names}. Lịch sử nộp bài được giữ nguyên.")
    else:
        await message.reply_text(
            f"✅ Đã nhập {len(problems)} bài: {names}. "
            "Bài ẩn cần dùng /publish tên_bài on để công bố.")


async def webapp_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bấm nút 📝 Nộp bài (inline) -> gửi bàn phím reply chứa nút mở Web App.
    Web App chỉ gửi được data về bot (sendData) khi mở từ nút keyboard."""
    query = update.callback_query
    await query.answer()
    try:
        name = urllib.parse.unquote((query.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        return
    if not name or not WEBAPP_URL:
        return
    wa_url = f"{WEBAPP_URL}/submit.html?p={urllib.parse.quote(name)}"
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"📝 <b>Nộp bài: {html.escape(name)}</b>\nBấm nút bên dưới để mở khung nhập code.",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📝 Mở khung nộp bài", web_app=WebAppInfo(url=wa_url))]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


async def on_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận code từ Web App 'Nộp bài' (Telegram.WebApp.sendData)."""
    msg = update.effective_message
    print(f"[webapp] update tới: message={'có' if msg else 'không'}, "
          f"web_app_data={bool(msg and msg.web_app_data)}")
    wad = msg.web_app_data if msg else None
    if not wad or not wad.data:
        return
    try:
        payload = json.loads(wad.data)
    except Exception:
        return
    if payload.get("t") != "submit":
        return
    name = str(payload.get("p", "")).strip()
    code = core.strip_fences(str(payload.get("c", "")))
    if not name or not code:
        await msg.reply_text("❌ Thiếu tên bài hoặc code, nộp lại giúp mình nhé.")
        return
    # Gửi tin trạng thái độc lập (không reply vào service message của Web App)
    # để các lần sửa tin sau đó đồng bộ như flow /submit.
    status_msg = await context.bot.send_message(
        chat_id=msg.chat_id,
        text=f"⏳ <b>Đang khởi tạo môi trường chấm bài <code>{html.escape(name)}</code>...</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove(),  # thu bàn phím nộp bài lại cho gọn
    )

    async def edit_update(text, **kw):
        nonlocal status_msg
        status_msg = await _safe_edit(status_msg, text, **kw)

    await _run_judge(name, code, update.effective_user, edit_update)


async def input_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, args = cmd_args(update.message.text)
    inp = core.strip_fences(" ".join(args)).strip().replace("```", "")
    if not access.valid_input(inp):
        await update.message.reply_text("❌ Input vượt quá 64 KiB.")
        return
    core.set_user_input(str(update.effective_user.id), inp)
    await update.message.reply_text(
        f"✅ <b>Đã nhận input:</b>\n{pre_limited(inp, 3000)}",
        parse_mode=ParseMode.HTML,
    )


async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, args = cmd_args(update.message.text)
    code = core.strip_fences(" ".join(args))
    inp = core.get_user_input(str(update.effective_user.id))
    if inp == "":
        await update.message.reply_text(
            "⚠️ <b>Chương trình không có input.</b> Dùng lệnh /input để nhập.",
            parse_mode=ParseMode.HTML,
        )
        return
    r = await core.run_once(code, inp)
    t = r["t"]
    if t == "ce":
        await update.message.reply_text("❌ <b>Lỗi biên dịch</b>\n" + pre_limited(r["stderr"], 3000), parse_mode=ParseMode.HTML)
    elif t == "rte":
        await update.message.reply_text("❌ <b>Lỗi khi chạy (Runtime Error)</b>\n" + pre_limited(r["stderr"], 3000), parse_mode=ParseMode.HTML)
    elif t == "tle":
        await update.message.reply_text("❌ <b>Lỗi:</b> Time Limit Exceeded (TLE) - Code chạy quá lâu.", parse_mode=ParseMode.HTML)
    elif t == "empty":
        await update.message.reply_text("⚠️ <b>Chương trình chạy xong nhưng không in ra gì.</b>", parse_mode=ParseMode.HTML)
    elif t == "sys":
        await update.message.reply_text("❌ Máy chấm chưa sẵn sàng hoặc code/input quá dài.")
    else:
        out = r["output"] + ("..." if r["truncated"] else "")
        await update.message.reply_text("✅ <b>Kết quả chạy code:</b>\n" + pre_limited(out, 3000), parse_mode=ParseMode.HTML)


async def problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, args = cmd_args(update.message.text)
    cats = core.list_visible_problems("telegram", update.effective_user.id)
    if not cats:
        await update.message.reply_text("Hiện tại chưa có bài tập nào.")
        return
    cat_names = list(cats.keys())

    if args:
        key = " ".join(args).strip()
        matched = None
        if key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < len(cat_names):
                matched = cat_names[idx]
        if matched is None:
            low = key.lower()
            exact = [c for c in cat_names if c.lower() == low]
            if exact:
                matched = exact[0]
            else:
                pref = [c for c in cat_names if c.lower().startswith(low)]
                if len(pref) == 1:
                    matched = pref[0]
                elif len(pref) > 1:
                    lines = "\n".join(
                        f"{i + 1}. <b>{html.escape(c)}</b>"
                        for i, c in enumerate(cat_names) if c in pref
                    )
                    await update.message.reply_text(
                        f"🔍 Có nhiều chuyên đề khớp với <code>{html.escape(key)}</code>:\n\n"
                        f"{lines}\n\nGõ lại với số thứ tự cho chắc nhé!",
                        parse_mode=ParseMode.HTML,
                    )
                    return
        if matched is None:
            await update.message.reply_text(
                f"❌ Không tìm thấy chuyên đề <code>{html.escape(key)}</code>.\n"
                "Gõ /problems để xem danh sách chuyên đề.",
                parse_mode=ParseMode.HTML,
            )
            return
        problem_list = "\n".join(f"- <code>{html.escape(i)}</code>" for i in cats[matched])
        await reply_long(update.message,
                         f"📚 <b>Chuyên đề: {html.escape(matched)}</b>\n\n"
                         f"{problem_list}\n\n"
                         "<i>Gõ /show tên_bài để xem đề.</i>")
        return

    cat_list = "\n".join(
        f"{i + 1}. <b>{html.escape(c)}</b> ({len(cats[c])} bài)"
        for i, c in enumerate(cat_names)
    )
    await update.message.reply_text(
        "📚 <b>Danh sách chuyên đề</b>\n\n"
        f"{cat_list}\n\n"
        "<i>Bấm nút bên dưới, hoặc gõ /problems kèm <b>số thứ tự</b> / vài ký tự đầu của tên.</i>\n"
        "Ví dụ: <code>/problems 1</code> hoặc <code>/problems quy</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=_cat_keyboard(cats),
    )


async def problems_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý nút bấm: chuyên đề -> danh sách bài -> xem đề (gọi _deliver_problem)."""
    query = update.callback_query
    await query.answer()
    cats = core.list_visible_problems("telegram", update.effective_user.id)
    cat_names = list(cats.keys())
    parts = (query.data or "").split(":")
    try:
        if len(parts) == 2 and parts[1] == "list":
            await query.edit_message_text(
                "📚 <b>Chọn chuyên đề:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=_cat_keyboard(cats))
        elif len(parts) == 3 and parts[1] == "cat":
            ci = int(parts[2])
            cname = cat_names[ci]
            await query.edit_message_text(
                f"📚 <b>Chuyên đề: {html.escape(cname)}</b>\n\n<i>Bấm để xem đề:</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=_prob_keyboard(cats[cname], ci))
        elif len(parts) == 4 and parts[1] == "show":
            ci, pi = int(parts[2]), int(parts[3])
            name = cats[cat_names[ci]][pi]
            try:
                await query.message.delete()  # chọn xong thì xóa menu cho gọn
            except BadRequest:
                pass
            await _deliver_problem(
                lambda text, **kw: context.bot.send_message(
                    chat_id=query.message.chat_id, text=text, **kw),
                name, update.effective_user.id)
    except BadRequest:
        pass  # bấm trùng nút / nội dung không đổi thì bỏ qua
    except (IndexError, ValueError):
        await query.edit_message_text(
            "⚠️ Danh sách đã thay đổi, gõ <code>/problems</code> lại nhé!",
            parse_mode=ParseMode.HTML)


async def category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    _, args = cmd_args(update.message.text)
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Cú pháp: <code>/category tên_bài tên_chuyên_đề</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    name, cat = args[0].strip(), args[1].strip()
    if core.set_category(name, cat):
        storage.record_admin_event("telegram", update.effective_user.id, "category", name)
        text = (f"✅ <b>Thành công:</b> Đã cập nhật chuyên đề <code>{html.escape(cat)}</code> "
                f"cho bài <code>{html.escape(name)}</code>.")
    else:
        text = err_not_found(name)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def addtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    _, args = cmd_args(update.message.text)
    if len(args) < 2:
        await update.message.reply_text("Cú pháp: /addtest tên_bài input_cố_định")
        return
    name, value = args[0].strip(), core.strip_fences(args[1])
    result = core.add_fixed_test(name, value)
    if result == "ok":
        storage.record_admin_event("telegram", update.effective_user.id, "addtest", name)
        await update.message.reply_text("✅ Đã thêm test cố định. Test này sẽ chạy trước test ngẫu nhiên.")
    else:
        await update.message.reply_text({
            "missing": "❌ Không tìm thấy bài.",
            "full": "❌ Bài đã có 10 test cố định.",
            "invalid": "❌ Input test phải có nội dung và tối đa 4 KiB.",
        }[result])


async def cleartests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    _, args = cmd_args(update.message.text)
    name = " ".join(args).strip()
    if not name or not core.set_problem_field(name, "fixed_tests", []):
        await update.message.reply_text("❌ Không tìm thấy bài. Dùng /cleartests tên_bài.")
        return
    storage.record_admin_event("telegram", update.effective_user.id, "cleartests", name)
    await update.message.reply_text("✅ Đã xóa các test cố định của bài.")


async def setlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    parts = update.message.text.split()
    if len(parts) != 5:
        await update.message.reply_text("Cú pháp: /setlimit tên_bài số_test giây RAM_MiB (1–10, 1–2, 64–128)")
        return
    try:
        count, seconds, memory = map(int, parts[2:])
    except ValueError:
        await update.message.reply_text("❌ Các giới hạn phải là số nguyên.")
        return
    name = parts[1]
    if not core.set_limits(name, count, seconds, memory):
        await update.message.reply_text("❌ Không tìm thấy bài hoặc giới hạn ngoài khoảng cho phép.")
        return
    storage.record_admin_event("telegram", update.effective_user.id, "setlimit", name)
    await update.message.reply_text(f"✅ {count} test, {seconds} giây/test, {memory} MiB.")


async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return
    parts = update.message.text.split()
    if len(parts) != 3 or parts[2].lower() not in ("on", "off"):
        await update.message.reply_text("Cú pháp: /publish tên_bài on|off")
        return
    name, enabled = parts[1], parts[2].lower() == "on"
    if not core.set_problem_field(name, "published", enabled):
        await update.message.reply_text("❌ Không tìm thấy bài.")
        return
    storage.record_admin_event("telegram", update.effective_user.id, "publish", name)
    await update.message.reply_text("✅ Bài đã công bố." if enabled else "✅ Bài đã ẩn với học sinh.")


async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Hướng dẫn sử dụng Bot cho Học sinh</b>\n"
        "Dưới đây là các lệnh bạn có thể sử dụng để làm bài và nộp bài:\n\n"
        "<b>1. Xem danh sách bài tập</b>\n"
        "<code>/problems</code>\nHiển thị các chuyên đề (bấm nút để chọn tới từng bài).\n\n"
        "<b>2. Xem đề bài</b>\n"
        "<code>/show tên_bài</code>\nVí dụ: <code>/show bai1</code>\n\n"
        "<b>3. Nhập dữ liệu đầu vào (Input)</b>\n"
        "<code>/input nội_dung_input</code>\nVí dụ: <code>/input 5 10</code>\n\n"
        "<b>4. Chạy thử code (Run)</b>\n"
        "<code>/run</code> + code trong khối ```\n"
        "Chạy code của bạn với input vừa nhập bằng lệnh /input.\n\n"
        "<b>5. Nộp bài (Submit)</b>\n"
        "<code>/submit tên_bài</code> + code trong khối ```\n"
        "Bot chấm số test đã cấu hình cho bài và báo kết quả chi tiết.\n"
        "Mẹo: bấm nút 📝 <b>Nộp bài</b> dưới mỗi đề, rồi bấm nút mở khung để nhập code cho đẹp.\n\n"
        "<b>6. Nộp file C++</b>\nGửi file .cpp (tối đa 64 KiB) kèm chú thích "
        "<code>/submit tên_bài</code>.\n\n"
        "<b>7. Kết quả</b>\n<code>/history</code> xem lịch sử; "
        "<code>/lastfail</code> xem input WA gần nhất; "
        "<code>/leaderboard</code> xem số bài AC.",
        parse_mode=ParseMode.HTML,
    )


async def admin_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠️ <b>Hướng dẫn sử dụng Bot cho Admin/Giáo viên</b>\n"
        "Các lệnh dành cho người quản lý để tạo đề và cấu hình bài chấm:\n\n"
        "<b>1. Tạo bài tập mới</b>\n"
        "<code>/create tên_bài</code>\nVí dụ: <code>/create bai1</code>\n\n"
        "<b>2. Thêm nội dung đề bài</b>\n"
        "<code>/question tên_bài</code> + nội dung đề trong khối ```\n\n"
        "<b>3. Thêm code lời giải chuẩn (Solution)</b>\n"
        "<code>/solution tên_bài</code> + code trong khối ```\n"
        "Code chuẩn sẽ được chạy với test sinh ra để lấy output đúng.\n\n"
        "<b>4. Thêm code sinh test (Generator)</b>\n"
        "<code>/gen tên_bài</code> + code trong khối ```\n"
        "Chương trình sinh input ngẫu nhiên cho số test được cấu hình.\n\n"
        "<b>5. Gán chuyên đề cho bài tập</b>\n"
        "<code>/category tên_bài tên_chuyên_đề</code>\n"
        "Ví dụ: <code>/category bai1 Quy hoạch động</code>\n\n"
        "<b>6. Test và công bố</b>\n"
        "<code>/addtest tên_bài input</code> thêm test cố định (tối đa 10).\n"
        "<code>/cleartests tên_bài</code> xóa test cố định.\n"
        "<code>/setlimit tên_bài số_test giây RAM_MiB</code> đặt giới hạn.\n"
        "<code>/publish tên_bài on|off</code> công bố/ẩn bài.\n\n"
        "<b>7. Nhập bài bằng JSON</b>\n"
        "Nhắn riêng bot file .json (tối đa 256 KiB) với caption "
        "<code>/importjson</code>. Gõ /importjson để xem cú pháp. "
        "Bài nhập mặc định ở trạng thái ẩn và không ghi đè bài cũ. "
        "Sửa bài đã có bằng file JSON đầy đủ với caption <code>/updatejson</code>.",
        parse_mode=ParseMode.HTML,
    )


async def how(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, args = cmd_args(update.message.text)
    topic = args[0].lower() if args else ""
    if not topic:
        await update.message.reply_text(
            "📚 <b>Hướng dẫn viết Code cấu hình bài tập</b>\n"
            "Dùng <code>/how chủ_đề</code> để xem chi tiết.\n"
            "Các chủ đề: <code>solution</code>, <code>gentest</code>, <code>checker</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    if topic in ("solution", "sol"):
        await reply_long(update.message,
                         "📖 <b>Hướng dẫn viết Solution</b>\n\n"
                         "<b>Code Lời Giải Chuẩn (Solution)</b>\n"
                         "- Viết bằng C++.\n"
                         "- Nhận input từ <code>cin</code>, in output ra <code>cout</code>.\n"
                         "- <b>Không cần</b> <code>freopen</code> vì hệ thống tự truyền dữ liệu.\n\n"
                         "<b>Mẫu ví dụ:</b>\n" + pre(core.SAMPLE_SOLUTION))
    elif topic in ("gentest", "gen", "gentests"):
        await reply_long(update.message,
                         "📖 <b>Hướng dẫn viết Gen Test</b>\n\n"
                         "<b>Code Sinh Test (Generator)</b>\n"
                         "- Viết bằng C++.\n"
                         "- Dùng hàm sinh số ngẫu nhiên (<code>mt19937_64</code> hoặc <code>rand()</code>).\n"
                         "- <b>Không đọc Input</b>. Tự sinh một bộ Input hoàn chỉnh và in ra bằng <code>cout</code>.\n\n"
                         "<b>Mẫu ví dụ:</b>\n" + pre(core.SAMPLE_GEN))
    elif topic == "checker":
        await reply_long(update.message,
                         "📖 <b>Hướng dẫn viết Checker</b>\n\n"
                         "<b>Code Chấm Bài (Checker)</b>\n"
                         "- Dùng cho bài có <i>nhiều đáp án đúng</i>. Bài chỉ có 1 đáp án thì hệ thống tự so sánh, "
                         "<b>không cần</b> viết Checker.\n"
                         "- <b>Cơ chế:</b> Bot gộp Input gốc, Output chuẩn và Output học sinh, ngăn cách bằng "
                         "<code>ENDINP</code> và <code>ENDOUT</code> rồi truyền qua <code>cin</code>.\n"
                         "- <b>Nhiệm vụ:</b> đọc Input đến <code>ENDINP</code>, đọc Output chuẩn đến <code>ENDOUT</code>, "
                         "phần còn lại là Output học sinh; tự viết logic kiểm tra.\n"
                         "- <b>Cực kỳ quan trọng:</b> học sinh đúng thì BẮT BUỘC in ra đúng chữ <code>AC</code> (viết hoa). "
                         "Sai thì in chữ khác hoặc không in gì.\n\n"
                         "<b>Mẫu ví dụ (bài in mảng không cần thứ tự):</b>\n" + pre(core.SAMPLE_CHECKER))
    else:
        await update.message.reply_text(
            "❌ <b>Lỗi:</b> Không tìm thấy chủ đề này. Các chủ đề: "
            "<code>solution</code>, <code>gentest</code>, <code>checker</code>",
            parse_mode=ParseMode.HTML,
        )


async def post_init(app):
    if not NOTIFY_CHAT_ID:
        return
    try:
        total = 24
        msg = None
        for i in range(1, total + 1):
            pct = i / total * 100
            bar = "█" * (i * 2) + "░" * ((total - i) * 2)
            text = f"🔄 <b>Đang khởi động hệ thống...</b>\n<pre>[{bar}] {pct:.1f}%</pre>"
            if msg is None:
                msg = await app.bot.send_message(
                    chat_id=int(NOTIFY_CHAT_ID), text=text, parse_mode=ParseMode.HTML)
            else:
                await msg.edit_text(text, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.8)
        await msg.delete()
        await app.bot.send_message(
            chat_id=int(NOTIFY_CHAT_ID),
            text="✅ <b>Khởi Động Hoàn Tất!</b>\n<b>Chào cả nhà, anh đã quay trở lại và lợi hại hơn xưa! 🚀</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        print("Notify failed:", e)


async def reload_reminder(context: ContextTypes.DEFAULT_TYPE):
    if NOTIFY_CHAT_ID:
        await context.bot.send_message(chat_id=int(NOTIFY_CHAT_ID), text="Lâm ơi, reload server đi")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("Nhắn riêng bot để xem lịch sử của bạn.")
        return
    rows = storage.recent_submissions("telegram", update.effective_user.id)
    lines = [f"{html.escape(name)}: {result.upper()} · seed {seed}"
             for name, result, seed, _ in rows]
    await update.effective_message.reply_text(
        "\n".join(lines) if lines else "Bạn chưa nộp bài nào.",
        parse_mode=ParseMode.HTML)


async def lastfail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("Nhắn riêng bot để xem input lỗi của bạn.")
        return
    row = storage.last_failure("telegram", update.effective_user.id)
    if not row:
        await update.effective_message.reply_text("Bạn chưa có lần nộp WA nào.")
        return
    name, seed, inp, expected = row
    await update.effective_message.reply_text(
        f"❌ <b>{html.escape(name)}</b> · seed <code>{seed}</code>\n"
        f"<b>Input:</b>\n{pre_limited(inp or '', 1400)}\n"
        f"<b>Output chuẩn:</b>\n{pre_limited(expected or '', 1400)}",
        parse_mode=ParseMode.HTML)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = storage.leaderboard()
    lines = [f"{i}. {platform}:{html.escape(uid)} — {score} bài AC"
             for i, (platform, uid, score) in enumerate(rows, 1)]
    await update.effective_message.reply_text(
        "\n".join(lines) if lines else "Chưa có bài AC.", parse_mode=ParseMode.HTML)


def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chat", chat))
    app.add_handler(CommandHandler("haogay", haogay))
    app.add_handler(CommandHandler("create", create))
    app.add_handler(CommandHandler("importjson", importjson))
    app.add_handler(CommandHandler("updatejson", updatejson))
    app.add_handler(CommandHandler("solution", solution))
    app.add_handler(CommandHandler("gen", gen))
    app.add_handler(CommandHandler("question", question))
    app.add_handler(CommandHandler("checker", checker))
    app.add_handler(CommandHandler("show", show))
    app.add_handler(CommandHandler("submit", submit))
    app.add_handler(MessageHandler(filters.Document.ALL, submit_document))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_web_app_data))
    app.add_handler(CommandHandler("input", input_cmd))
    app.add_handler(CommandHandler("run", run))
    app.add_handler(CommandHandler("problems", problems))
    app.add_handler(CallbackQueryHandler(problems_menu, pattern=r"^prob:"))
    app.add_handler(CallbackQueryHandler(webapp_menu, pattern=r"^wasub:"))
    app.add_handler(CommandHandler("category", category))
    app.add_handler(CommandHandler("addtest", addtest))
    app.add_handler(CommandHandler("cleartests", cleartests))
    app.add_handler(CommandHandler("setlimit", setlimit))
    app.add_handler(CommandHandler("publish", publish))
    app.add_handler(CommandHandler("guide", guide))
    app.add_handler(CommandHandler("admin_guide", admin_guide))
    app.add_handler(CommandHandler("how", how))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("lastfail", lastfail))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    if app.job_queue:
        app.job_queue.run_repeating(reload_reminder, interval=48 * 3600, first=48 * 3600)
