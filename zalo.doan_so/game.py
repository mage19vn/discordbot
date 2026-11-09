"""Example Zalo game: guess a number in the current chat."""

import random
import time

from zalo_ui import card


def _active(ctx):
    if "answer" in ctx.state and time.monotonic() - ctx.state.get("updated_at", 0) >= 900:
        ctx.state.clear()
    return "answer" in ctx.state


def start(ctx):
    if _active(ctx):
        return card("🔎 Con số vẫn đang chờ bạn", f"Một số từ 1 đến 10. Cả chat cùng đoán nhé!\nCòn {ctx.state['remaining']} lần thử.",
                    "/doso <1-10> → Đoán số")
    ctx.state["answer"] = random.randint(1, 10)
    ctx.state.update(owner=ctx.user_id, remaining=5, guesses=[], updated_at=time.monotonic())
    return card("🔢 Một con số bí mật", "Mình đang nghĩ đến một số từ 1 đến 10.\nBạn có 5 lần để tìm ra nó!",
                "/doso 5 → Thử số 5\n/help doan_so → Cách chơi")


def guess(ctx):
    if not _active(ctx):
        return "Chưa có lượt chơi. Gõ /doanso để bắt đầu."
    try:
        number = int(ctx.args.strip())
    except ValueError:
        return "Gõ /doso <số từ 1 đến 10>."
    if number < 1 or number > 10:
        return "Số cần nằm trong khoảng 1 đến 10."
    if number in ctx.state["guesses"]:
        return f"Số {number} đã được đoán. Hãy chọn số khác; bạn chưa mất lượt."
    ctx.state["guesses"].append(number)
    ctx.state["remaining"] -= 1
    ctx.state["updated_at"] = time.monotonic()
    answer = ctx.state["answer"]
    if number == answer:
        used = 5 - ctx.state["remaining"]
        ctx.state.clear()
        name = getattr(ctx, "display_name", "") or "Người chơi"
        return card(f"🎉 {name} đoán đúng!", f"Con số bí mật là {answer}.\nChỉ cần {used} lần thử — làm tốt lắm!",
                    "/doanso → Chơi thêm lượt nữa")
    remaining = ctx.state["remaining"]
    if not remaining:
        ctx.state.clear()
        return card("🌱 Hết lượt rồi, thử lại nhé!", f"Đáp án là {answer}.\nLần sau bạn sẽ tìm ra thôi!", "/doanso → Thử lại")
    hint = "lớn hơn" if number < answer else "nhỏ hơn"
    history = ", ".join(map(str, ctx.state["guesses"]))
    return card(f"{'↗️' if number < answer else '↘️'} Thử một số {hint} {number}",
                f"Còn {remaining} lần thử\nĐã đoán: {history}",
                "/doso <1-10> → Đoán tiếp")


def stop(ctx):
    if not _active(ctx):
        return "Chưa có lượt chơi. Gõ /doanso để bắt đầu."
    if ctx.user_id != ctx.state["owner"]:
        return "Chỉ người mở lượt được kết thúc. Bạn vẫn có thể đoán bằng /doso <số>."
    answer = ctx.state["answer"]
    ctx.state.clear()
    return card("👋 Đã khép lại lượt chơi", f"Con số bí mật là {answer}.", "/doanso → Bắt đầu lượt mới")
