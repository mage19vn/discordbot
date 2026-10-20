import asyncio
import os
import random

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import core
import access
import storage

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
NOTIFY_CHANNEL_ID = int(os.getenv("DISCORD_NOTIFY_CHANNEL_ID", "0") or 0)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=">", intents=intents)

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


def create_bot():
    return bot


@bot.event
async def on_ready():
    print(f"Bot {bot.user} đã sẵn sàng nhận lệnh!")
    if not NOTIFY_CHANNEL_ID:
        return
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        print("Không tìm thấy kênh. Hãy kiểm tra lại DISCORD_NOTIFY_CHANNEL_ID.")
        return
    msg = None
    total_steps = 24
    for i in range(1, total_steps + 1):
        percent = (i / total_steps) * 100
        filled = "█" * (i * 2)
        empty = "░" * ((total_steps - i) * 2)
        desc = f"**🔄 Đang khởi động hệ thống...**\n```ini\n[{filled}{empty}] {percent:.1f}%\n```"
        embed = discord.Embed(description=desc, color=discord.Color.teal())
        if msg is None:
            msg = await channel.send(embed=embed)
        else:
            await msg.edit(embed=embed)
        await asyncio.sleep(0.8)
    if msg:
        await msg.delete()
    await channel.send(embed=discord.Embed(
        title="✅ Khởi Động Hoàn Tất!",
        description="**Chào cả nhà, anh đã quay trở lại và lợi hại hơn xưa! 🚀**",
        color=discord.Color.green(),
    ))


@bot.command()
async def chat(ctx, *, code: str):
    code = core.strip_fences(code)
    print(f'Code: "\n{code}"')
    await ctx.send(embed=discord.Embed(
        description=f"💬 **Đang xử lý đoạn hội thoại:**\n```\n{code}\n```",
        color=discord.Color.blue(),
    ))


@bot.command()
async def Haogay(ctx):
    try:
        file = discord.File("haogay.png", filename="haogay.png")
        embed = discord.Embed(color=discord.Color.blue())
        embed.set_image(url="attachment://haogay.png")
        await ctx.send(file=file, embed=embed)
    except FileNotFoundError:
        await ctx.send("❌ Mình không tìm thấy file `haogay.png`. Bạn nhớ lưu ảnh vào cùng thư mục với code nhé!")


@bot.command()
@commands.check(lambda ctx: access.discord_admin(ctx.author))
async def create(ctx, *, name: str):
    name = name.strip()
    if core.create_problem(name, ctx.author.id):
        storage.record_admin_event("discord", ctx.author.id, "create", name)
        desc, color = f"✅ **Thành công:** Đã tạo bài `{name}`.", discord.Color.green()
    else:
        desc, color = f"❌ **Lỗi:** Có bài tên `{name}` rồi nhen.", discord.Color.red()
    await ctx.send(embed=discord.Embed(description=desc, color=color))


async def _set_field(ctx, name: str, code: str, field: str, label: str):
    name = name.strip()
    if core.set_problem_field(name, field, core.strip_fences(code)):
        storage.record_admin_event("discord", ctx.author.id, field, name)
        desc = f"✅ **Thành công:** Đã cập nhật {label} cho bài `{name}`."
        color = discord.Color.green()
    else:
        desc = f"❌ **Lỗi:** Không tìm thấy bài `{name}`."
        color = discord.Color.red()
    await ctx.send(embed=discord.Embed(description=desc, color=color))


@bot.command()
@commands.check(lambda ctx: access.discord_admin(ctx.author))
async def solution(ctx, name: str, *, code: str):
    await _set_field(ctx, name, code, "solution", "Code Giải (Solution)")


@bot.command()
@commands.check(lambda ctx: access.discord_admin(ctx.author))
async def gen(ctx, name: str, *, code: str):
    await _set_field(ctx, name, code, "gen_test", "Code Sinh Test (Generator)")


@bot.command()
@commands.check(lambda ctx: access.discord_admin(ctx.author))
async def question(ctx, name: str, *, code: str):
    await _set_field(ctx, name, code, "question", "Đề Bài")


@bot.command()
@commands.check(lambda ctx: access.discord_admin(ctx.author))
async def checker(ctx, name: str, *, code: str):
    await _set_field(ctx, name, code, "checker", "Code Checker")


@bot.command()
async def show(ctx, *, name: str):
    await _deliver_problem(ctx.send, name.strip(), ctx.author.id)


def _safe_text(value, limit=100):
    value = discord.utils.escape_mentions(discord.utils.escape_markdown(value))
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _question_chunks(question, limit=3900):
    """Split long Markdown without leaving an open code fence in an embed."""
    chunks, current, fenced = [], "", False
    for line in question.splitlines(keepends=True):
        while line:
            suffix = "\n```" if fenced else ""
            room = limit - len(current) - len(suffix)
            opening_only = fenced and current.startswith("```") and current.count("\n") == 1
            if len(line) > room and current and not opening_only:
                chunks.append(current + suffix)
                current = "```\n" if fenced else ""
                continue
            part, line = line[:room], line[room:]
            current += part
            if not line and part.lstrip().startswith("```"):
                fenced = not fenced
            if line:
                chunks.append(current + ("\n```" if fenced else ""))
                current = "```\n" if fenced else ""
    if current:
        chunks.append(current + ("\n```" if fenced else ""))
    return chunks or ["*Chưa có nội dung đề bài.*"]


async def _deliver_problem(send, name, user_id):
    """Shared problem display for prefix, slash, and browser selection."""
    p = core.visible_problem(name, "discord", user_id)
    if p is None:
        await send(embed=discord.Embed(
            description=f"❌ **Lỗi:** Không tìm thấy bài `{_safe_text(name, 120)}`.",
            color=discord.Color.red(),
        ))
        return
    for index, chunk in enumerate(_question_chunks(p.get("question", "")), 1):
        embed = discord.Embed(
            title=f"📝 Đề bài: {_safe_text(name, 220)}" if index == 1 else None,
            description=chunk, color=discord.Color.blue())
        if index == 1:
            embed.set_footer(text=(f"{p.get('test_count', 10)} test · "
                                   f"{p.get('time_limit', 2)} giây/test · "
                                   f"{p.get('memory_limit', 128)} MiB · "
                                   f"v{p.get('version', 1)}"))
        await send(embed=embed, view=SubmitView(name) if index == 1 else None)


async def _safe_edit_discord(status_msg, embed):
    """Sửa tin nhắn trạng thái; nếu không sửa được thì gửi tin mới."""
    try:
        await status_msg.edit(embed=embed)
        return status_msg
    except (discord.NotFound, discord.HTTPException) as e:
        print(f"[judge] không sửa được tin nhắn Discord: {e} -> gửi tin mới")
        return await status_msg.channel.send(embed=embed)


async def _run_judge(name, code, author, on_update):
    """Chạy core.judge và báo tiến trình qua on_update(embed) —
    dùng chung cho lệnh >submit và Modal nộp bài."""
    async for ev in core.judge(name, code, "discord", author.id):
        t = ev["t"]
        if t == "not_found":
            await on_update(discord.Embed(
                description=f"❌ **Lỗi:** Không tìm thấy bài `{name}`.",
                color=discord.Color.red(),
            ))
            return
        if t == "status":
            if ev["msg"] == "testing":
                await on_update(discord.Embed(
                    description=f"🚀 **Code biên dịch thành công. Đang chạy {ev.get('count', 10)} test...**",
                    color=discord.Color.blue(),
                ))
            continue
        if t == "ce":
            who = {"user": "Code của bạn", "solution": "Code Solution",
                   "gen": "Code Gen Test", "checker": "Code Checker"}[ev["who"]]
            title = "❌ Compilation Error" if ev["who"] == "user" else "⚠️ Lỗi hệ thống"
            await on_update(discord.Embed(
                title=title,
                description=f"**{who} bị lỗi biên dịch:**\n```cpp\n{ev['stderr'][:1800]}\n```",
                color=discord.Color.red() if ev["who"] == "user" else discord.Color.orange(),
            ))
            return
        if t == "sys":
            msgs = {
                "gen_tle": "❌ **Lỗi hệ thống:** TLE khi sinh test (Generator bị lặp vô hạn).",
                "gen_rte": f"❌ **Lỗi hệ thống:** Trình sinh test (Gen) gặp lỗi (RTE).\n```\n{ev.get('detail', '')[:1000]}\n```",
                "gen_empty": "⚠️ **Cảnh báo:** Trình sinh test (Gen) tạo ra input rỗng.",
                "sol_tle": "❌ **Lỗi hệ thống:** TLE ở code Solution chuẩn.",
                "sol_rte": f"❌ **Lỗi hệ thống:** Code Solution chuẩn gặp lỗi (RTE).\n```\n{ev.get('detail', '')[:1000]}\n```",
                "no_compiler": "❌ **Lỗi hệ thống:** Máy chấm chưa cài `g++`, không biên dịch được. Báo admin cài giúp nhé!",
                "gen_missing": "❌ Bài chưa có đủ test cố định và chưa có generator.",
                "sandbox": "❌ Trình chạy chấm bài chưa sẵn sàng. Báo quản trị viên kiểm tra cấu hình.",
                "busy": "⏳ Máy chấm đang bận. Vui lòng nộp lại sau.",
                "code_limit": "❌ Code phải có nội dung và không vượt quá 64 KiB.",
            }
            await on_update(discord.Embed(
                description=msgs[ev["msg"]], color=discord.Color.red(),
            ))
            return
        if t == "rte":
            await on_update(discord.Embed(
                title=f"❌ Runtime Error (RTE) tại Test {ev['test']}",
                description=f"{random.choice(MESSAGE_REPLY_TEMPLATES['rte'])}\n```\n{ev['stderr'][:1800]}\n```",
                color=discord.Color.red(),
            ))
            return
        if t == "tle":
            await on_update(discord.Embed(
                description=f"{random.choice(MESSAGE_REPLY_TEMPLATES['tle'])}\n"
                            f"❌ **Time Limit Exceeded (TLE) tại Test {ev['test']}** "
                            f"(quá {ev.get('limit', 2)} giây).",
                color=discord.Color.red(),
            ))
            return
        if t == "wa":
            await on_update(discord.Embed(
                title=f"❌ Wrong Answer (WA) tại Test {ev['test']}",
                description=f"{random.choice(MESSAGE_REPLY_TEMPLATES['wa'])}\n"
                            f"**Input sinh ra:**\n```\n{ev['inp'][:500]}\n```\n"
                            f"**Output mong đợi:**\n```\n{ev['sol'][:500]}\n```\n"
                            f"**Output của bạn:**\n```\n{ev['out'][:500]}\n```\n"
                            f"Seed: `{ev.get('seed', '')}`",
                color=discord.Color.red(),
            ))
            return
        if t == "ac":
            await on_update(discord.Embed(
                title="✅ ACCEPTED!",
                description=f"{random.choice(MESSAGE_REPLY_TEMPLATES['ac'])}\n"
                            f"Chúc mừng <@{author.id}>, code của bạn đã vượt qua "
                            f"{ev.get('count', 10)}/{ev.get('count', 10)} test bài `{name}`.",
                color=discord.Color.green(),
            ))
            return


class SubmitModal(discord.ui.Modal):
    """Khung nhập code nộp bài — bản Discord của Telegram Web App."""
    def __init__(self, problem_name: str):
        super().__init__(title=f"📝 Nộp bài: {problem_name}"[:45])
        self.problem_name = problem_name
        self.code_input = discord.ui.TextInput(
            label="Code C++ (tối đa 4000 ký tự)",
            style=discord.TextStyle.paragraph,
            placeholder="Dán code vào đây... Code dài hơn thì dùng lệnh >submit",
            max_length=4000,
            required=True,
        )
        self.add_item(self.code_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.problem_name
        code = core.strip_fences(self.code_input.value)
        await interaction.response.send_message(embed=discord.Embed(
            description=f"⏳ **Đang khởi tạo môi trường chấm bài `{name}`...**",
            color=discord.Color.gold(),
        ))
        status_msg = await interaction.original_response()

        async def edit_update(embed):
            nonlocal status_msg
            status_msg = await _safe_edit_discord(status_msg, embed)

        await _run_judge(name, code, interaction.user, edit_update)


class SubmitView(discord.ui.View):
    """Nút 📝 Nộp bài gắn dưới mỗi đề."""
    def __init__(self, problem_name: str):
        super().__init__(timeout=None)
        self.problem_name = problem_name

    @discord.ui.button(label="📝 Nộp bài", style=discord.ButtonStyle.primary)
    async def submit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SubmitModal(self.problem_name))


@bot.command()
async def submit(ctx, name: str, *, code: str):
    name = name.strip()
    code = core.strip_fences(code)
    status_msg = await ctx.send(embed=discord.Embed(
        description=f"⏳ **Đang khởi tạo môi trường chấm bài `{name}`...**",
        color=discord.Color.gold(),
    ))

    async def edit_update(embed):
        nonlocal status_msg
        status_msg = await _safe_edit_discord(status_msg, embed)

    await _run_judge(name, code, ctx.author, edit_update)


@bot.command(name="input")
async def input_cmd(ctx, *, inp_temp: str):
    inp = inp_temp.strip().replace("```", "")
    if not access.valid_input(inp):
        await ctx.send("❌ Input vượt quá 64 KiB.")
        return
    core.set_user_input(str(ctx.author.id), inp)
    await ctx.send(embed=discord.Embed(
        description=f"✅ **Đã nhận input:**\n```\n{inp}\n```",
        color=discord.Color.green(),
    ))


@bot.command()
async def run(ctx, *, code: str):
    code = core.strip_fences(code)
    inp = core.get_user_input(str(ctx.author.id))
    if inp == "":
        await ctx.send(embed=discord.Embed(
            description="⚠️ **Chương trình không có input.** Dùng lệnh `>input` để nhập.",
            color=discord.Color.orange(),
        ))
        return
    r = await core.run_once(code, inp)
    t = r["t"]
    if t == "ce":
        await ctx.send(embed=discord.Embed(
            title="❌ Lỗi biên dịch", description=f"```cpp\n{r['stderr'][:1900]}\n```",
            color=discord.Color.red(),
        ))
    elif t == "rte":
        await ctx.send(embed=discord.Embed(
            title="❌ Lỗi khi chạy (Runtime Error)", description=f"```\n{r['stderr'][:1900]}\n```",
            color=discord.Color.red(),
        ))
    elif t == "tle":
        await ctx.send(embed=discord.Embed(
            description="❌ **Lỗi:** Time Limit Exceeded (TLE) - Code chạy quá lâu.",
            color=discord.Color.red(),
        ))
    elif t == "empty":
        await ctx.send(embed=discord.Embed(
            description="⚠️ **Chương trình chạy xong nhưng không in ra gì.**",
            color=discord.Color.orange(),
        ))
    elif t == "sys":
        await ctx.send("❌ Máy chấm chưa sẵn sàng hoặc code/input quá dài.")
    else:
        out = r["output"] + ("..." if r["truncated"] else "")
        await ctx.send(embed=discord.Embed(
            title="✅ Kết quả chạy code:", description=f"```\n{out}\n```",
            color=discord.Color.green(),
        ))


def _match_category(cats, key):
    names = list(cats)
    if key.isdecimal() and 1 <= int(key) <= len(names):
        return names[int(key) - 1], []
    exact = [name for name in names if name.casefold() == key.casefold()]
    if exact:
        return exact[0], []
    matches = [name for name in names if name.casefold().startswith(key.casefold())]
    return (matches[0], []) if len(matches) == 1 else (None, matches)


class BrowserSelect(discord.ui.Select):
    def __init__(self, browser, choices, category):
        self.browser = browser
        self.choices = choices
        self.category = category
        options = [discord.SelectOption(label=name[:100], value=str(index),
                                        description=(f"{count} bài" if count is not None else None))
                   for index, (name, count) in enumerate(choices)]
        super().__init__(placeholder="Chọn chuyên đề" if category is None else "Chọn bài để xem đề",
                         options=options, min_values=1, max_values=1)

    async def callback(self, interaction):
        name = self.choices[int(self.values[0])][0]
        await self.browser.choose(interaction, name, self.category)


class ProblemBrowserView(discord.ui.View):
    """Paged category → problem → statement navigation for one Discord user."""
    PAGE_SIZE = 25

    def __init__(self, owner_id, category=None):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.category = category
        self.page = 0

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Dùng `>problems` để mở danh sách của bạn.", ephemeral=True)
            return False
        return True

    def render(self):
        cats = core.list_visible_problems("discord", self.owner_id)
        if self.category not in cats:
            self.category = None
        if self.category is None:
            items = [(name, len(problems)) for name, problems in cats.items()]
            title = "📚 Danh sách chuyên đề"
            hint = "Chọn chuyên đề bên dưới, hoặc dùng `>problems 1` / `>problems quy`."
        else:
            items = [(name, None) for name in cats[self.category]]
            title = f"📚 Chuyên đề: {_safe_text(self.category, 220)}"
            hint = "Chọn bài bên dưới để xem đề, hoặc dùng `>show tên_bài`."
        self.page = min(self.page, max(0, (len(items) - 1) // self.PAGE_SIZE))
        start = self.page * self.PAGE_SIZE
        shown = items[start:start + self.PAGE_SIZE]
        lines = [f"{start + i + 1}. **{_safe_text(name, 100)}**" +
                 (f" ({count} bài)" if count is not None else "")
                 for i, (name, count) in enumerate(shown)]
        embed = discord.Embed(title=title,
                              description="\n".join(lines) + "\n\n" + hint,
                              color=discord.Color.blue())
        embed.set_footer(text=f"Trang {self.page + 1}/{max(1, (len(items) + 24) // 25)}")
        self.clear_items()
        if shown:
            self.add_item(BrowserSelect(self, shown, self.category))
        if self.category is not None:
            back = discord.ui.Button(label="⬅️ Chuyên đề", style=discord.ButtonStyle.secondary)
            back.callback = self.back
            self.add_item(back)
        if self.page > 0:
            prev = discord.ui.Button(label="◀ Trước", style=discord.ButtonStyle.secondary)
            prev.callback = self.previous
            self.add_item(prev)
        if start + self.PAGE_SIZE < len(items):
            next_button = discord.ui.Button(label="Sau ▶", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)
        return embed

    async def choose(self, interaction, name, category):
        cats = core.list_visible_problems("discord", interaction.user.id)
        if category is None:
            if name not in cats:
                await interaction.response.send_message("Danh sách đã thay đổi. Gõ `>problems` lại nhé.", ephemeral=True)
                return
            self.category, self.page = name, 0
            await interaction.response.edit_message(embed=self.render(), view=self)
            return
        if name not in cats.get(category, []):
            await interaction.response.send_message("Bài đã thay đổi. Gõ `>problems` lại nhé.", ephemeral=True)
            return

        async def send(**kwargs):
            if interaction.response.is_done():
                await interaction.followup.send(**kwargs, ephemeral=True)
            else:
                await interaction.response.send_message(**kwargs, ephemeral=True)
        await _deliver_problem(send, name, interaction.user.id)

    async def back(self, interaction):
        self.category, self.page = None, 0
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def previous(self, interaction):
        self.page -= 1
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def next_page(self, interaction):
        self.page += 1
        await interaction.response.edit_message(embed=self.render(), view=self)


@bot.command()
async def problems(ctx, *, key: str = None):
    cats = core.list_visible_problems("discord", ctx.author.id)
    if not cats:
        await ctx.send("Hiện tại chưa có bài tập nào.")
        return
    category = None
    if key:
        category, matches = _match_category(cats, key.strip())
        if category is None:
            if matches:
                lines = "\n".join(f"- {_safe_text(name, 100)}" for name in matches[:25])
                await ctx.send(f"🔍 Có nhiều chuyên đề khớp `{_safe_text(key, 100)}`:\n{lines}\nDùng số thứ tự hoặc tên đầy đủ.")
            else:
                await ctx.send(f"❌ Không tìm thấy chuyên đề `{_safe_text(key, 100)}`. Gõ `>problems` để xem danh sách.")
            return
    view = ProblemBrowserView(ctx.author.id, category)
    await ctx.send(embed=view.render(), view=view)


@bot.command()
@commands.check(lambda ctx: access.discord_admin(ctx.author))
async def category(ctx, name: str, *, cat: str):
    name, cat = name.strip(), cat.strip()
    if core.set_category(name, cat):
        storage.record_admin_event("discord", ctx.author.id, "category", name)
        desc = f"✅ **Thành công:** Đã cập nhật chuyên đề `{cat}` cho bài `{name}`."
        color = discord.Color.green()
    else:
        desc = f"❌ **Lỗi:** Không tìm thấy bài `{name}`."
        color = discord.Color.red()
    await ctx.send(embed=discord.Embed(description=desc, color=color))


@bot.command()
async def guide(ctx):
    embed = discord.Embed(
        title="📖 Hướng dẫn sử dụng Bot cho Học sinh",
        description="Dưới đây là các lệnh bạn có thể sử dụng để làm bài và nộp bài:",
        color=discord.Color.green(),
    )
    embed.add_field(name="1. Xem danh sách bài tập",
                    value="`>problems` chọn chuyên đề → bài → đề. Có thể dùng `>problems 1` hoặc `>problems quy`.", inline=False)
    embed.add_field(name="2. Xem đề bài",
                    value="`>show <tên_bài>`\nVí dụ: `>show bai1`\nHiển thị nội dung đề bài tương ứng.", inline=False)
    embed.add_field(name="3. Nhập dữ liệu đầu vào (Input)",
                    value="`>input <nội_dung_input>`\nCung cấp input để bạn có thể chạy code thử nghiệm trên bot.\nVí dụ: `>input 5 10`", inline=False)
    embed.add_field(name="4. Chạy thử code (Run)",
                    value="`>run <code_của_bạn>`\nChạy code của bạn với input vừa nhập bằng lệnh `>input`.\nNhớ đặt code trong block.", inline=False)
    embed.add_field(name="5. Nộp bài (Submit)",
                    value="`>submit <tên_bài> <code_của_bạn>`\nVí dụ: `>submit bai1 <code_của_bạn>`\nBot chấm theo số test đã cấu hình cho bài. Bấm nút 📝 **Nộp bài** dưới đề để mở khung nhập code.", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def admin_guide(ctx):
    embed = discord.Embed(
        title="🛠️ Hướng dẫn sử dụng Bot cho Admin/Giáo viên",
        description="Dưới đây là các lệnh dành cho người quản lý để tạo đề và cấu hình bài chấm:",
        color=discord.Color.red(),
    )
    embed.add_field(name="1. Tạo bài tập mới",
                    value="`>create <tên_bài>`\nVí dụ: `>create bai1`\nKhởi tạo bài tập mới trên hệ thống.", inline=False)
    embed.add_field(name="2. Thêm nội dung đề bài",
                    value="`>question <tên_bài> <nội_dung_đề>`\nCập nhật nội dung câu hỏi, yêu cầu bài toán.", inline=False)
    embed.add_field(name="3. Thêm code lời giải chuẩn (Solution)",
                    value="`>solution <tên_bài> <code_chuẩn>`\nThêm code giải chuẩn. Code này sẽ được chạy với các test sinh ra để lấy output đúng nhằm so sánh với bài của học sinh.", inline=False)
    embed.add_field(name="4. Thêm code sinh test (Generator)",
                    value="`>gen <tên_bài> <code_sinh_test>`\nThêm chương trình sinh test. Chương trình này sẽ in ra dữ liệu đầu vào (input) ngẫu nhiên mỗi lần chạy, giúp tự động tạo 10 test cases cho học sinh.", inline=False)
    embed.add_field(name="5. Gán chuyên đề cho bài tập",
                    value="`>category <tên_bài> <tên_chuyên_đề>`\nVí dụ: `>category bai1 Quy hoạch động`\nGắn bài tập vào chuyên đề để phân loại trong danh sách `>problems`.", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def how(ctx, topic: str = None):
    if not topic:
        await ctx.send(embed=discord.Embed(
            title="📚 Hướng dẫn viết Code cấu hình bài tập",
            description="Sử dụng lệnh `>how <chủ_đề>` để xem hướng dẫn chi tiết.\nCác chủ đề hỗ trợ: `solution`, `gentest`, `checker`",
            color=discord.Color.blue(),
        ))
        return
    topic = topic.lower()
    if topic in ["solution", "sol"]:
        desc = ("**Code Lời Giải Chuẩn (Solution)**\n"
                "- Viết bằng C++.\n"
                "- Nhận input từ luồng chuẩn (`cin`) và in output ra luồng chuẩn (`cout`).\n"
                "- **Không cần** sử dụng lệnh đọc ghi file (`freopen`) vì hệ thống tự động truyền dữ liệu ảo.\n\n"
                "**Mẫu ví dụ:**\n```cpp\n" + core.SAMPLE_SOLUTION + "\n```")
        await ctx.send(embed=discord.Embed(title="📖 Hướng dẫn viết Solution", description=desc, color=discord.Color.green()))
    elif topic in ["gentest", "gen", "gentests"]:
        desc = ("**Code Sinh Test (Generator)**\n"
                "- Viết bằng C++.\n"
                "- Sử dụng các hàm sinh số ngẫu nhiên (ví dụ `mt19937_64` hoặc `rand()`).\n"
                "- **Không đọc bất kỳ Input nào**. Nhiệm vụ của code là tự động sinh ra một bộ Input hoàn chỉnh và in ra bằng `cout`.\n"
                "- Kết quả in ra sẽ được dùng làm Input cho cả Code Chuẩn và Code của Học sinh.\n\n"
                "**Mẫu ví dụ:**\n```cpp\n" + core.SAMPLE_GEN + "\n```")
        await ctx.send(embed=discord.Embed(title="📖 Hướng dẫn viết Gen Test", description=desc, color=discord.Color.green()))
    elif topic == "checker":
        desc = ("**Code Chấm Bài (Checker)**\n"
                "- Thường dùng cho các bài toán có *nhiều đáp án đúng* (Output không cố định). Nếu bài toán chỉ có 1 đáp án, hệ thống đã tự động so sánh nên **không cần** viết Checker.\n"
                "- **Cơ chế:** Bot sẽ gộp Input gốc, Output chuẩn (magCode) và Output của học sinh lại, ngăn cách bằng chữ `ENDINP` và `ENDOUT` rồi truyền vào qua `cin`.\n"
                "- **Nhiệm vụ:** Đọc Input cho đến khi gặp `ENDINP`, đọc Output của magCode cho đến khi gặp `ENDOUT`, phần còn lại là Output học sinh. Dựa vào đó bạn tự viết logic kiểm tra xem học sinh làm đúng không.\n"
                "- **Lưu ý cực kỳ quan trọng:** Nếu học sinh đúng, bạn BẮT BUỘC phải in ra màn hình đúng chữ `AC` (Viết hoa). Nếu sai, in ra bất kỳ chữ gì khác (hoặc không in gì) đều bị tính là Wrong Answer.\n\n"
                "**Mẫu ví dụ (Cho bài toán in ra mảng không cần theo thứ tự):**\n```cpp\n" + core.SAMPLE_CHECKER + "\n```")
        await ctx.send(embed=discord.Embed(title="📖 Hướng dẫn viết Checker", description=desc, color=discord.Color.green()))
    else:
        await ctx.send(embed=discord.Embed(
            title="❌ Lỗi",
            description="Không tìm thấy chủ đề này. Các chủ đề hỗ trợ: `solution`, `gentest`, `checker`",
            color=discord.Color.red(),
        ))


@tasks.loop(hours=48)
async def reload_reminder():
    if reload_reminder.current_loop == 0 or not NOTIFY_CHANNEL_ID:
        return
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if channel:
        await channel.send("Lâm ơi, reload server đi")


@reload_reminder.before_loop
async def before_reload_reminder():
    await bot.wait_until_ready()


@bot.command(name="history")
async def history(ctx):
    rows = storage.recent_submissions("discord", ctx.author.id)
    lines = [f"{name}: {result.upper()}" for name, result, _, _ in rows]
    await ctx.send("\n".join(lines) if lines else "Bạn chưa nộp bài nào.")


@bot.command(name="leaderboard")
async def leaderboard(ctx):
    rows = storage.leaderboard()
    lines = [f"{i}. {platform}:{uid} — {score} bài AC"
             for i, (platform, uid, score) in enumerate(rows, 1)]
    await ctx.send("\n".join(lines) if lines else "Chưa có bài AC.")


@bot.tree.command(name="bai", description="Xem đề bài")
async def slash_problem(interaction: discord.Interaction, name: str):
    async def send(**kwargs):
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs, ephemeral=True)
        else:
            await interaction.response.send_message(**kwargs, ephemeral=True)
    await _deliver_problem(send, name.strip(), interaction.user.id)


@slash_problem.autocomplete("name")
async def problem_names(interaction: discord.Interaction, current: str):
    names = [name for group in core.list_visible_problems("discord", interaction.user.id).values()
             for name in group]
    return [discord.app_commands.Choice(name=name[:100], value=name)
            for name in names if current.casefold() in name.casefold() and len(name) <= 100][:25]


@bot.tree.command(name="lichsu", description="Xem lịch sử nộp bài của bạn")
async def slash_history(interaction: discord.Interaction):
    rows = storage.recent_submissions("discord", interaction.user.id)
    lines = [f"{name}: {result.upper()}" for name, result, _, _ in rows]
    await interaction.response.send_message(
        "\n".join(lines) if lines else "Bạn chưa nộp bài nào.", ephemeral=True)


@bot.tree.command(name="bangxephang", description="Bảng xếp hạng")
async def slash_leaderboard(interaction: discord.Interaction):
    rows = storage.leaderboard()
    lines = [f"{i}. {platform}:{uid} — {score} bài AC"
             for i, (platform, uid, score) in enumerate(rows, 1)]
    await interaction.response.send_message("\n".join(lines) if lines else "Chưa có bài AC.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("⛔ Lệnh này chỉ dành cho quản trị viên.")
    else:
        raise error


async def setup_hook():
    reload_reminder.start()
    try:
        await bot.tree.sync()
    except discord.HTTPException as exc:
        print(f"Không đồng bộ được slash commands: {exc}")


bot.setup_hook = setup_hook
