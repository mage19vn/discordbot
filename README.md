# MagOJ — bot chấm bài Discord và Telegram

Bot dùng một lõi chấm C++ cho cả Discord và Telegram. Mỗi bài có đề, solution,
generator và checker tùy chọn. Mỗi bài có thể cấu hình 1–10 test. Telegram có Web App
trong `submit.html`; Discord có nút nộp bài và một số slash command.

## Cài trên KataBump

Cần chọn server Python và phiên bản Python 3.10+ trên panel. Theo cấu hình
server hiện tại, `g++` đã có sẵn; không cần Docker, quyền root, `systemd`
hay `prlimit`. Upload các file dự án vào `/home/container`, sao cho
`main.py` và `requirements.txt` ở ngay thư mục gốc. Có thể dùng tab Files
hoặc SFTP; không upload `.venv` từ máy cá nhân. Trong tab Startup, đặt
`PY FILE` là `main.py`. KataBump sẽ tự
chạy `pip install -r requirements.txt` trước khi chạy bot.

Đặt `TELEGRAM_BOT_TOKEN` trong Environment Variables của panel hoặc trong
file `.env` ở `/home/container`. Hiện bạn chỉ dùng Telegram, nên để trống
`DISCORD_TOKEN`. Điền `TELEGRAM_ADMIN_IDS` bằng Telegram user ID dạng số
của người được tạo/sửa bài; nhiều ID ngăn bằng dấu phẩy. Nếu để trống,
không ai có quyền sửa bài. `TELEGRAM_NOTIFY_CHAT_ID` và
`MAGOJ_WEBAPP_URL` là tùy chọn. URL Web App phải là HTTPS công khai trỏ đến
thư mục chứa `submit.html`; chỉ điền URL gốc, không thêm tên file.

Sau khi upload, bấm Start ở tab Console và đọc log khởi động. Chỉ chạy một
instance với mỗi Telegram token; hai instance dùng cùng token sẽ gây
`telegram.error.Conflict`. Gói miễn phí phải gia hạn mỗi 4 ngày. Khi cập
nhật, upload đè file mã nguồn rồi Restart; giữ nguyên `data.sqlite3`. Gói
hiện tại có 308 MB RAM, 716 MB disk và 25% CPU; không lưu file bài nộp lâu
dài. Các file tạm do trình chấm tạo được xóa sau mỗi lượt.
Nếu panel cho mở shell, có thể chạy `python3 main.py --check` để kiểm tra
cấu hình mà không đăng nhập Telegram hoặc in giá trị token. Khi bot offline,
kiểm tra hạn gia hạn, log Console, `PY FILE`, token và việc có instance thứ
hai đang dùng cùng token.

Máy phát triển cá nhân có thể dùng venv:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Chạy local:

```sh
.venv/bin/python main.py
```

`MAGOJ_JUDGE_BACKEND=local` là mặc định cho KataBump. `MAGOJ_MAX_JOBS=1`
giới hạn một lượt chấm hoặc chạy thử tại một thời điểm; lượt chờ quá 3 giây
sẽ nhận thông báo bận. Có thể điều chỉnh nếu server có đủ RAM/CPU. Mỗi lần
chạy C++ bị giới hạn 2 giây, 128 MiB RAM, 128 KiB output. Biên dịch tối đa
30 giây và 256 MiB vùng nhớ ảo (cần cho `bits/stdc++.h`). Code và input tối
đa 64 KiB. Với RAM tổng 308 MB, theo dõi Console khi dùng đề C++ nặng.

Trình chạy local chỉ giới hạn tài nguyên và lọc biến môi trường trực tiếp.
Code C++ vẫn cùng quyền filesystem và mạng với process bot, nên không phù
hợp cho người dùng không tin cậy trên server chứa token hoặc dữ liệu nhạy
cảm. Muốn cô lập thực sự cần chuyển khâu chấm sang máy/worker hỗ trợ container;
trên máy đó đặt `MAGOJ_JUDGE_BACKEND=docker` và chuẩn bị image GCC đã ghim
digest trong `sandbox.py`. Không bật Docker trên KataBump khi server không hỗ
trợ container.

## Dữ liệu và sao lưu

Lần chạy đầu, bot nhập toàn bộ `data.json` cũ vào SQLite `data.sqlite3` (bao
gồm 19 bài trong repository). Tệp JSON gốc vẫn được giữ để đối chiếu. Các
lần sau, SQLite là nguồn dữ liệu chính; bot không ghi ngược vào JSON.
Trước lần chạy đầu sau nâng cấp, sao lưu và giữ bản `data.json` đang dùng
trên KataBump; đừng upload đè bằng bản cũ từ repository nếu đã thêm bài trực
tiếp trên server. Bot sẽ nhập chính bản JSON hiện có tại `/home/container`.

Trên KataBump, giữ `data.sqlite3` trong `/home/container` khi cập nhật
code. Nếu muốn dùng thư mục dữ liệu riêng, đặt `MAGOJ_DB_PATH` thành đường
dẫn tuyệt đối. Không xóa database trước khi cập nhật; xóa sẽ khiến bot nhập
lại bản JSON cũ và mất bài/submission mới. Khi backup lúc bot đang chạy, dùng
SQLite backup API thay vì chỉ copy file chính vì dữ liệu có thể còn trong WAL.

Lịch sử nộp bài lưu nền tảng, user ID, tên bài, kết quả, thời điểm và seed.
Khi WA, SQLite còn lưu tối đa 4 KiB input gây lỗi và output chuẩn cho
`/lastfail`. Bot không lưu code người nộp hay tệp `.cpp` tải từ Telegram.
Generator mới nên đọc biến `MAGOJ_SEED` để tái tạo test; ví dụ trong `core.py`
đã làm vậy. Generator cũ dùng đồng hồ thời gian sẽ không tái tạo được chỉ từ
seed đã lưu. Bảng xếp hạng đếm số bài khác nhau đạt AC của mỗi tài khoản
trên từng nền tảng.

Mỗi bài mới có số test, giới hạn thời gian/RAM, trạng thái công bố, phiên bản,
tác giả và ngày tạo. Bài cũ mặc định công bố với 10 test, 2 giây/test và
128 MiB RAM. Admin thêm test cố định bằng `/addtest`; bot chạy chúng trước
test ngẫu nhiên. Nếu toàn bộ số test là test cố định, không cần generator.
Admin dùng `/setlimit tên_bài số_test giây RAM_MiB` trong khoảng 1–10 test,
1–2 giây và 64–128 MiB; dùng `/publish tên_bài off` để ẩn bài đang soạn.
Các bài ẩn không hiện trong danh sách, đề hoặc luồng nộp của học sinh.

## Lệnh

| Chức năng | Discord | Telegram |
| --- | --- | --- |
| Tạo bài (admin) | `>create` | `/create` |
| Sửa đề/solution/generator/checker (admin) | `>question`, `>solution`, `>gen`, `>checker` | `/question`, `/solution`, `/gen`, `/checker` |
| Phân loại (admin) | `>category` | `/category` |
| Test và giới hạn (admin) | — | `/addtest`, `/cleartests`, `/setlimit`, `/publish` |
| Xem đề/danh sách | `>show`, `>problems`, `/bai` slash | `/show`, `/problems` |
| Nhập input/chạy thử | `>input`, `>run` | `/input`, `/run` |
| Nộp bài | `>submit`, nút dưới đề | `/submit`, Web App, hoặc file `.cpp` tối đa 64 KiB với caption `/submit tên_bài` |
| Lịch sử cá nhân | `>history`, `/lichsu` slash | `/history`, `/lastfail` |
| Bảng xếp hạng | `>leaderboard`, `/bangxephang` slash | `/leaderboard` |

Code C++ đặt trong khối code ba dấu backtick. Slash command Discord đồng bộ
khi bot khởi động; lệnh toàn cục có thể cần thời gian mới hiện trên Discord.

## Phát triển và kiểm thử

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Test dùng SQLite tạm và trình chạy local; không cần token hoặc kết nối tới
Discord/Telegram. Chúng kiểm tra nhập dữ liệu cũ, phân quyền, giới hạn tải,
biên dịch/chạy/chấm bài, AC/WA/CE/RTE/TLE, checker, test cố định, ẩn bài,
migration schema, kiểm tra cấu hình và nộp file. Đăng nhập
thực tế trên KataBump vẫn cần kiểm tra với token của bạn.
