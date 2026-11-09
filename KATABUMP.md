# Chạy MagOJ trên KataBump

## Sửa ngay lỗi `No module named 'dotenv'`

Tên thư viện cài đặt là `python-dotenv`, tên import là `dotenv`. Đừng cài gói
tên `dotenv`. Nếu có shell/terminal Python, chạy bằng đúng interpreter của server:

```sh
python -m pip install --no-cache-dir -r requirements.txt
python main.py
```

Nếu báo `.venv/bin/python: No module named pip`, bản bootstrap mới tự thử
`python -m ensurepip --upgrade` trong đúng môi trường đang chạy. Nếu image không
có `ensurepip`, nó tải `get-pip.py` từ `https://bootstrap.pypa.io/get-pip.py` rồi
cài pip vào cùng interpreter. Đây là hai cách khởi tạo pip được
[tài liệu pip hỗ trợ](https://pip.pypa.io/en/stable/installation/).
Không dùng `--user` bên trong `.venv`, không xóa `.venv` hay dữ liệu của bạn.
Upload đè `bootstrap.py` mới hoặc giải nén ZIP mới rồi Restart.
Nếu cả hai cách đều lỗi, kiểm tra kết nối tới PyPA/PyPI và quyền ghi `.venv`,
hoặc nhờ KataBump cung cấp image Python có pip.

Console gửi lệnh cho bot không nhất thiết là shell. Nếu không có shell, upload
bản mới gồm `main.py`, `bootstrap.py`, `paths.py`, `requirements.txt` và các file
còn lại từ ZIP bên dưới, rồi Restart. `main.py` mới dùng thư viện chuẩn để kiểm
tra dependencies trước khi import bot. Nếu thiếu hoặc sai phiên bản, nó gọi pip
bằng chính interpreter đang chạy rồi khởi động lại. Nếu pip lỗi, đọc thông báo
pip phía trên dòng lỗi cuối; kiểm tra Python 3.12, dung lượng trống và kết nối PyPI.
Không cần chạy pip nếu bộ dependencies đúng phiên bản đã có sẵn.

## Upload và khởi động

1. Trên máy phát triển chạy `python build_katabump.py` để tạo
   `dist/magoj-katabump.zip`. ZIP có `main.py` trực tiếp ở gốc, gồm cả game Zalo.
2. Trên KataBump chọn server Python. Trong Startup chọn Python **3.12** và
   **PY FILE = `main.py`**. Dependencies yêu cầu Python tối thiểu 3.10.
3. Bấm Stop trước khi cập nhật, tải bản sao `.env`, `data.sqlite3` và `data.json`
   nếu có. Giải nén ZIP vào `/home/container`, không tạo thêm thư mục bao ngoài.
   ZIP không chứa `.env`, SQLite, bản `data.json` ở gốc, `.venv` hoặc file biên dịch.
4. Lần đầu: copy `.env.example` thành `.env` trong Files và điền token. Khi cập
   nhật, giữ `.env` đang dùng. Biến môi trường có sẵn được ưu tiên hơn `.env`.
5. Start và đọc Console. Có thể mất vài phút khi cài dependencies lần đầu.

Các thư mục `zalo.*` nằm cạnh `main.py`, không nằm trong thư mục `zalo/`.
Đường dẫn `.env`, SQLite và JSON được tính từ thư mục mã nguồn kể cả khi thư mục
làm việc của panel khác đi.

## Cấu hình bot

```dotenv
ZALO_BOT_TOKEN=token_cua_ban
ZALO_ADMIN_IDS=id_admin_zalo
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_IDS=
DISCORD_TOKEN=
DISCORD_ADMIN_IDS=
MAGOJ_JUDGE_BACKEND=local
MAGOJ_MAX_JOBS=1
```

Điền token của bot muốn chạy; để trống các bot còn lại. Có thể bật cả ba trên
cùng tiến trình, nhưng cần theo dõi RAM và CPU của gói đang dùng. ID quản trị
Telegram/Discord là số; Zalo dùng chuỗi ID từ `/id`. Nhiều ID cách nhau dấu phẩy.
Discord cần bật Message Content Intent trong Developer Portal. Mỗi token chỉ
nên có một instance polling/gateway đang chạy.

Game Zalo: `/help`, `/games`, `/carohelp`. Luyện C++: `/help cpp`.
`MAGOJ_WEBAPP_URL` chỉ dùng khi đã host `submit.html` tại một URL HTTPS công khai;
chạy bot không tự tạo website hay mở cổng HTTP trên KataBump. Có thể để trống URL
và nộp code trực tiếp qua tin nhắn/file. `TELEGRAM_PROXY` là tùy chọn.

## Kiểm tra và chạy C++

Nếu có shell, kiểm tra bằng:

```sh
python main.py --check
python main.py --check-runner
```

`--check` kiểm tra cấu hình mà không đăng nhập bot; `--check-runner` còn biên dịch
và chạy chương trình tính `21 → 42`. Cần token đã điền trong `.env` để bước kiểm
tra cấu hình hợp lệ. `--no-install` tắt cài dependencies tự động cho một lần chạy.

Chọn `MAGOJ_JUDGE_BACKEND=local` trên Linux khi image có `g++`. Không dùng Docker,
`apt install`, quyền root hoặc `systemd` trong container KataBump thông thường.
Nếu image không có GCC, bot và game vẫn khởi động; lệnh chạy/nộp C++ báo chưa có
compiler. Chọn image có GCC hoặc nhờ hỗ trợ KataBump; pip không thể cài `g++`.
Không mặc định mọi image Python đều có GCC.

Mặc định chỉ chấm một bài tại một thời điểm, giới hạn 2 giây/chạy và 128 MiB cho
chương trình. Biên dịch giới hạn 30 giây, 256 MiB vùng nhớ ảo. Giới hạn này không
phải tổng RAM của tiến trình bot; nếu bị panel kill do RAM, cần giảm số bot đang
bật hoặc dùng gói có tài nguyên phù hợp. Không vô hiệu hóa resource limits.

Runner local không cô lập filesystem/mạng khỏi tiến trình bot. Chỉ nhận C++ từ
người tin cậy trên máy chứa token; với người dùng công khai cần worker cô lập ở
máy khác hỗ trợ container.

## Dữ liệu, cập nhật và khôi phục

SQLite mặc định ở `/home/container/data.sqlite3`. Bản ZIP không ghi đè dữ liệu
đang có. Lần khởi tạo đầu, bot ưu tiên `data.json` ở gốc để nhập dữ liệu cũ; nếu
không có thì dùng `examples/seed-data.json` trong ZIP. Nhập JSON chỉ diễn ra một
lần cho mỗi database. Đừng xóa SQLite để cập nhật code.

Khi Stop hoàn toàn, sao lưu SQLite và các file `-wal`, `-shm` nếu còn, `.env`,
`data.json` và game tùy chỉnh. Không chỉ copy SQLite chính lúc bot vẫn đang ghi.
Nếu bản cập nhật lỗi, Stop rồi giải nén bản mã nguồn trước, giữ database hiện tại
và Start. Điểm/ván game trong bộ nhớ mất khi Restart. Stop gửi SIGTERM; bản mới
đóng các kết nối bot trước khi thoát.

Nếu panel báo Offline, xem lỗi đầu tiên trong Console, kiểm tra gia hạn gói,
Python/PY FILE, token, dung lượng/RAM và instance trùng token. Không in hoặc chụp
token trong log hỗ trợ.

Tham khảo chính thức:
[Startup và .env](https://docs.katabump.com/launch-your-bot/environment-variables/),
[quản lý server](https://docs.katabump.com/hosting/manage-your-server/).
