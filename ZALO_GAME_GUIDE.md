# Viết game cho bot Zalo

Đặt mỗi game trong một thư mục ở **gốc dự án** có tên bắt đầu bằng `zalo.`.
Bot tìm các thư mục này khi khởi động; sau khi thêm hoặc sửa game, hãy khởi động
lại bot. Mã Python trong thư mục được nạp và chạy với quyền của tiến trình bot,
vì vậy chỉ cài game từ nguồn tin cậy.

Thư mục mẫu chạy được ngay: [`zalo.doan_so`](zalo.doan_so). Cấu trúc tối thiểu:

```text
zalo.doan_so/
├── der.json
└── game.py
```

`der.json` khai báo các lệnh. Mỗi khóa trong `commands` là tên lệnh sau dấu
`/`, viết bằng chữ thường ASCII, số hoặc `_`, bắt đầu bằng chữ hoặc `_`.
Tên lệnh phải duy nhất giữa các game và không được trùng lệnh có sẵn của bot.

Hai trường tùy chọn ở cấp gốc: `title` là tên game hiển thị trong `/games`,
`help` là đoạn hướng dẫn mở đầu khi dùng `/help <tên_folder_sau_zalo.>`.
Ví dụ: `"title": "Đoán số", "help": "Gửi /doanso rồi /doso 5 để đoán."`.
Nếu bỏ qua, bot dùng tên thư mục và tự liệt kê các lệnh. Có thể dùng
`from zalo_ui import card` và trả `card("🎮 TÊN GAME", "Nội dung", "Lệnh tiếp theo")`
để tạo bố cục tin nhắn thống nhất. `card` trả văn bản thuần, không cần HTML.

```json
{
  "commands": {
    "doanso": {
      "description": "bắt đầu trò đoán số từ 1 đến 10",
      "handler": "game.py:start"
    },
    "doso": {
      "description": "đoán số: /doso <số>",
      "handler": "game.py:guess"
    }
  }
}
```

`handler` có dạng `tên_file.py:tên_hàm`; file Python phải nằm ngay trong thư
mục game. Có thể khai báo nhiều lệnh trỏ tới các hàm hoặc file `.py` khác nhau.
Nếu một file hay lệnh trong thư mục sai cấu hình, bot ghi cảnh báo và bỏ qua
toàn bộ thư mục đó; các game hợp lệ vẫn được nạp. `/help` sẽ liệt kê lệnh game.

Hàm nhận một tham số `ctx`:

- `ctx.chat_id`, `ctx.user_id`: ID chat và người gửi, đều là chuỗi.
- `ctx.display_name`: tên hiển thị người gửi (có thể rỗng). Dùng tên này khi
  hiển thị kết quả; dùng `ctx.user_id` để kiểm tra lượt và quyền. Đây là tên
  văn bản, không phải mention gửi thông báo @.
- `ctx.args`: phần văn bản sau tên lệnh, giữ nguyên xuống dòng.
- `ctx.state`: dict dùng chung cho các lệnh của **game này trong chat này**;
  dữ liệu chỉ tồn tại trong bộ nhớ và có thể mất khi bot khởi động hoặc kết nối lại.
- `await ctx.reply(text)`: gửi phản hồi ngay. Hàm cũng có thể `return` một
  chuỗi để bot gửi sau khi xử lý. Nếu trả `None`, bot không tự gửi tin nhắn.

Ví dụ file `game.py` đơn giản:

```python
def start(ctx):
    ctx.state["answer"] = 7
    return "Đã bắt đầu. Gõ /doso <số>."


async def guess(ctx):
    if not ctx.args.strip().isdigit():
        await ctx.reply("Hãy nhập một số.")
        return
    if int(ctx.args) == ctx.state.get("answer"):
        ctx.state.pop("answer", None)
        return "Chính xác!"
    return "Chưa đúng."
```

Hàm có thể là `def` hoặc `async def`. Xử lý tác vụ lâu bằng `async def` để
không chặn vòng polling. Tin nhắn game được chia theo giới hạn Zalo giống
các lệnh sẵn có. Trong khi người dùng đang gửi code nhiều phần cho `/run` hoặc
`/submit`, bot xem mọi tin nhắn khác là code cho đến khi họ gửi `/done` hoặc
`/cancel`.
