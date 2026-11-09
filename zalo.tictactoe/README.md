# Tic Tac Toe trên Zalo

Bàn cờ 3×3, đánh đủ 3 ô liên tiếp theo hàng, cột hoặc đường chéo để thắng.
Mỗi chat có một ván riêng. Trạng thái mất khi bot khởi động hoặc kết nối lại.

1. Gửi `/batdau` để tạo ván và cầm X.
2. Người thứ hai gửi `/thamgia` để cầm O; hoặc chủ ván gửi `/choibot de|vua|kho`
   (mặc định khó). Bot dễ đi ngẫu nhiên, vừa đôi lúc sai, khó chọn nước tối ưu.
3. X đi trước. Gửi `/chono <1-9>` để chọn ô theo sơ đồ bên dưới.
4. Khi thắng hoặc hòa, hai người cùng gửi `/choilai` để tái đấu; chơi với bot
   chỉ cần người chơi xác nhận. X luôn đi trước. `/batdau` mở phòng mới.

`/carohelp` hướng dẫn ngay trong chat; `/help tictactoe` liệt kê các lệnh.
`/banco` xem lại bàn cờ, `/dauhang` nhận thua, `/diemcaro` xem 10 người có kết quả
tốt nhất trong chat. Mỗi ván hoàn thành được tính đúng một lần; bảng điểm chỉ
lưu trong bộ nhớ và mất khi bot khởi động/kết nối lại.

`/dungcaro` dành cho chủ ván để đóng phòng chờ hoặc ván đã kết thúc. Khi đang
chơi, phải dùng `/dauhang` để ghi nhận kết quả. Ván chờ/đang chơi hết hạn sau
15 phút không có người vào hoặc nước đi hợp lệ; xem bàn cờ không gia hạn ván.

```text
1|2|3
-----
4|5|6
-----
7|8|9
```

Bot dùng minimax để chọn nước đi. Chế độ hai người cần cùng chat nhóm;
hãy mention hoặc reply bot khi gửi lệnh để Zalo chuyển tin tới bot.
Khởi động lại bot sau khi cài hoặc sửa thư mục này; `/help` sẽ liệt kê các lệnh.
