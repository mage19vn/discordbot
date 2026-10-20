Judge Bot — 1 lõi, 2 nền tảng
Bot chấm bài C++ tự động: tạo đề, nộp bài, sinh test ngẫu nhiên,
chấm 10 test cases, hỗ trợ checker cho bài nhiều đáp án.
Cấu trúc
File
Vai trò
core.py
Lõi dùng chung: lưu dữ liệu, biên dịch, chạy test, chấm bài. Không dính Discord/Telegram.
bot_discord.py
Adapter Discord: lệnh >create, >submit... gọi vào core.
bot_telegram.py
Adapter Telegram: lệnh /create, /submit... gọi vào core.
main.py
Chạy 2 bot song song trong cùng 1 process.
Dữ liệu bài tập và input dùng chung qua data.json nên làm đề trên
Discord rồi chấm bài trên Telegram (hoặc ngược lại) đều được.
Cài đặt
pip install -r requirements.txt
Cần g++ để biên dịch code C++.
Cấu hình
Copy .env.example thành .env rồi điền token:
DISCORD_TOKEN=
DISCORD_NOTIFY_CHANNEL_ID=
TELEGRAM_BOT_TOKEN=
TELEGRAM_NOTIFY_CHAT_ID=
Chỉ điền token của nền tảng nào muốn chạy — bot sẽ tự bỏ qua
nền tảng còn lại.
Chạy
python main.py
Lệnh
Chức năng
Discord
Telegram
Tạo bài
>create tên_bài
/create tên_bài
Thêm đề
>question tên_bài ...
/question tên_bài ...
Thêm solution
>solution tên_bài ...
/solution tên_bài ...
Thêm gen test
>gen tên_bài ...
/gen tên_bài ...
Thêm checker
>checker tên_bài ...
/checker tên_bài ...
Xem đề
>show tên_bài
/show tên_bài
Danh sách bài
>problems
/problems
Gán chuyên đề
>category tên_bài ...
/category tên_bài ...
Nhập input
>input ...
/input ...
Chạy thử
>run ...
/run ...
Nộp bài
>submit tên_bài ...
/submit tên_bài ...
Hướng dẫn
>guide / >admin_guide / >how
/guide / /admin_guide / /how
Code C++ đặt trong khối ``` (khối code) như bản Discord cũ.