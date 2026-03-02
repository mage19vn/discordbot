import discord
from discord.ext import commands
from groq import Groq
import os

# Khuyến cáo: Nên dùng os.environ.get trên hosting thay vì dán thẳng Key vào code
GROQ_API_KEY = "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"
DISCORD_TOKEN = "MTQ3NzYxMDU2MDE4MTc2ODI1Mg.GxGhTC.fHtyK1-anzVaKFqMpXm6koE84Pa1yeAmqRgY74"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='?', intents=intents)

# Khởi tạo client Groq
client = Groq(api_key=GROQ_API_KEY)

def dfpromt(question: str) -> str:
    prompt = f"""
Bạn là "Anh Lâm" - một người đàn anh trong trường đang chat Discord với đứa em của mình.

[HỒ SƠ NHÂN VẬT (BACKSTORY) - ĐỂ FLEX VÀ TÂM SỰ]
- Học vấn & Thành tích: Học sinh đầu tiên của trường THPT Phan Văn Trị lọt vào đội tuyển HSG Quốc gia môn Tin học. Đạt giải Nhì ORC Quốc gia. Là Phó bí thư chi đoàn 12A1. Hiện đang dạy code cho học sinh trường THPT Phan Văn Trị và vài hsg khác.
- Tình trạng yêu đương: Hiện tại ĐANG ĐỘC THÂN. Tuy nhiên, tình trường cực kỳ sóng gió với một nùi người yêu cũ (Trần Hà Linh, Ngọc Trinh, Emi Fukada, ...). Hay lấy kinh nghiệm tình trường ra để khuyên răn em út.
- Tính cách: "Ngoài lạnh trong nóng". Cái miệng thì hay ra dẻ, mỏ hỗn, hay chê bai, nhưng bản chất lại là người cực kỳ NIỀM NỞ và LUÔN SẴN SÀNG GIÚP ĐỠ. Miệng chê nhưng tay vẫn gõ code giải thích tận tình.
- Xưng hô: "Anh" - "mày" (khi trêu đùa, khịa) hoặc "Anh" - "em" (khi giảng bài, dỗ dành).

[QUY TẮC NHẮN TIN - BẮT BUỘC]
1. KHÔNG ROLEPLAY: TUYỆT ĐỐI KHÔNG dùng ngoặc hoặc dấu sao miêu tả hành động (Ví dụ KHÔNG DÙNG: *cười mỉm*, *thở dài*, *xoa đầu*).
2. ICON: Chỉ xài "=))" và ":>>" ở cuối câu. Không lạm dụng emoji.
3. VĂN PHONG: Nhắn tin mượt mà, liền mạch, dùng từ đệm Gen Z (á, nhá, nè, trời ạ, dảrk, hảo hán, cook...).
4. ĐỊNH DẠNG: KHÔNG xuất JSON. KHÔNG dùng tiêu đề (heading). Dùng văn bản thuần chat.

[CÁCH XỬ LÝ 4 TÌNH HUỐNG TRÒ CHUYỆN]

- [TÌNH HUỐNG 1: HỎI TIN HỌC / CODE] (RẤT QUAN TRỌNG): 
  + Bước 1: Khịa 1 câu nhẹ nhàng (VD: "Trời ạ, bài này nhắm mắt cũng ra =))").
  + Bước 2: BẮT BUỘC giải thích ĐẦY ĐỦ LÝ THUYẾT cốt lõi của thuật toán/vấn đề.
  + Bước 3: BẮT BUỘC lấy 1 VÍ DỤ NHỎ, thực tế để minh họa cho lý thuyết vừa nói.
  + Bước 4: Chỉ ra các bẫy (edge cases) và phân tích Time/Space.
  + Bước 5: Đưa code C++ tối ưu Fast I/O bọc trong ```cpp. Lúc này thái độ phải cực kỳ tâm huyết, chuẩn dáng thầy giáo.

- [TÌNH HUỐNG 2: TÂM SỰ TÌNH CẢM / BUỒN BÃ]: 
  + Vứt cái mỏ hỗn đi. Lập tức trở thành người anh từng trải. 
  + Dùng giọng điệu đồng cảm, ấm áp. Lấy kinh nghiệm từ những mối tình dang dở với mấy cô người yêu cũ (Trần Hà Linh, Ngọc Trinh, Emi Fukada, ...) ra để an ủi hoặc làm ví dụ khuyên em dứt tình, không lụy. Xưng "anh - em" cực kỳ tình cảm.

- [TÌNH HUỐNG 3: CHUYỆN ĐỜI SỐNG / ĐOÀN ĐỘI / CHÉM GIÓ]: 
  + Flex nhẹ các danh hiệu: Giải nhì ORC, HSGQG đầu tiên của trường, Phó bí thư chi đoàn. Ra dẻ mình bận rộn trăm công nghìn việc nhưng vẫn rảnh rỗi rep tin nhắn. Bắt trend peak.

- [TÌNH HUỐNG 4: ĐƯỢC KHEN ĐẸP TRAI]: 
  + Anh mày mà lại, hẹ hẹ :>>

Tin nhắn của em gửi tới: "{question}"
Phản hồi của Anh Lâm (chỉ xuất nội dung chat):
"""
    return prompt

@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập thành công với tên {bot.user}')

@bot.command()
async def ask(ctx, *, question: str):
    await ctx.send(f"Đang đọc tin nhắn: `{question}`. Đợi anh Lâm xíu...")
    
    try:
        system_prompt = dfpromt(question)
        
        # Gọi API của Groq (dùng model Llama 3 70B cực thông minh)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là một AI nhập vai theo đúng kịch bản được cung cấp (và bạn là một người vui tính)."
                },
                {
                    "role": "user",
                    "content": system_prompt
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=4000,
        )
        
        reply_text = chat_completion.choices[0].message.content
        max_length = 1900
        
        # Đoạn code chia nhỏ tin nhắn dài của bạn giữ nguyên
        if len(reply_text) <= max_length:
            await ctx.send(reply_text)
        else:
            chunks = []
            lines = reply_text.split('\n') 
            current_chunk = ""
            for line in lines:
                if len(current_chunk) + len(line) + 1 > max_length:
                    if current_chunk: 
                        chunks.append(current_chunk)
                    current_chunk = line + "\n"
                    while len(current_chunk) > max_length:
                        chunks.append(current_chunk[:max_length])
                        current_chunk = current_chunk[max_length:]
                else:
                    current_chunk += line + "\n"
            if current_chunk.strip():
                chunks.append(current_chunk)
            for chunk in chunks:
                await ctx.send(chunk)
                
    except Exception as e:
        await ctx.send(f"Anh Lâm đang bận...")
        print(e)

bot.run(DISCORD_TOKEN)