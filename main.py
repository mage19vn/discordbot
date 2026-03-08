import discord
from discord.ext import commands
from discord.ext import tasks
import datetime
from groq import Groq
import random
import time
import os
import requests
import asyncio
import redis

# Khuyến cáo: Nên dùng os.environ.get trên hosting thay vì dán thẳng Key vào code
GROQ_API_KEY = os.environ.get("GROQ_KEY").strip()
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN_CHATBOT").strip()
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL is None:
    print("❌ LỖI: Chưa có biến môi trường REDIS_URL!")
else:
    db = redis.from_url(REDIS_URL, decode_responses=True)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='>', intents=intents)
# Khởi tạo client Groq
client = Groq(api_key=GROQ_API_KEY)

tz_vn = datetime.timezone(datetime.timedelta(hours=7))
thoi_gian_gui = datetime.time(hour=18, minute=0, second=0, tzinfo=tz_vn)

money = {}
noitu_games = {}

vietnamese_dict = set()
used = set()
print("Đang tải từ điển tiếng Việt vào bộ nhớ...")

url = "https://raw.githubusercontent.com/duyet/vietnamese-wordlist/master/Viet39K.txt"

try:
    response = requests.get(url, timeout=10)
    response.encoding = 'utf-8'
    if response.status_code == 200:
        for line in response.text.splitlines():
            word = line.strip().lower()
            if len(word.split()) == 2:
                vietnamese_dict.add(word)
        print(f"✅ Đã tải thành công {len(vietnamese_dict)} từ ghép 2 tiếng vào RAM!")
    else:
        print(f"❌ Lỗi khi tải từ điển: Code {response.status_code}")
except Exception as e:
    print(f"❌ Không thể kết nối để tải từ điển: {e}")
    
def lay_nghia_tu(tu):
    tu_chuan = tu.strip().lower()
    url_wiki = f"https://vi.wiktionary.org/w/api.php?action=query&prop=extracts&titles={tu_chuan}&format=json&explaintext=1"
    try:
        res = requests.get(url_wiki, timeout=3).json() # Timeout ngắn để game không bị giật lag
        pages = res.get("query", {}).get("pages", {})
        for pid, pdata in pages.items():
            if pid != "-1":
                ext = pdata.get("extract", "").strip()
                if ext:
                    # Rút gọn nghĩa: Chỉ lấy dòng đầu tiên chứa nội dung, bỏ qua các tiêu đề
                    lines = [l.strip() for l in ext.split('\n') if l.strip() and not l.startswith('=')]
                    if lines:
                        nghia = lines[0]
                        # Cắt bớt nếu dòng giải nghĩa quá dài
                        return nghia[:150] + "..." if len(nghia) > 150 else nghia
    except:
        pass
    return "Từ này hiểm quá, từ điển chưa kịp cập nhật giải nghĩa =))"

def openfile():
    try:
        with open("money.money", "r") as f:
            a = f.read().strip().split('\n')
        for i in a:
            if ':' in i:
                key, val = i.split(':')
                money[key] = int(val)
    except FileNotFoundError:
        pass # Nếu chưa có file thì bỏ qua

openfile()

def writefile():
    with open("money.money", "w") as f:
        for i in money:
            f.write(f'{i}:{money[i]}\n')

def lac_xuc_xac():
    d1 = random.randint(1, 10000000000) % 6
    d2 = random.randint(1, 10000000000) % 6
    d3 = random.randint(1, 10000000000) % 6
    total = d1 + d2 + d3
    
    ket_qua = "Xỉu" if total % 2 else "Tài"
    
    return d1, d2, d3, total, ket_qua  

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
5. Hãy ghi nhớ: Đông Duy thích Hoa Đăng, Tuấn An thích Cẩm Tú, Thành Lộc si mê Bảo Ngọc, còn anh Lâm thì yêu anime.

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

@tasks.loop(time=thoi_gian_gui)
async def tu_dong_chuc_8_3():
    hom_nay = datetime.datetime.now(tz_vn)
    
    if hom_nay.day == 8 and hom_nay.month == 3:
        print("Đến 18h ngày 8/3 rồi! Bắt đầu tự động gửi tin nhắn...")
        
        loi_chuc = """||@everyone||
🌸 **Chúc Mừng Ngày Quốc Tế Phụ Nữ 8/3!** 🌸
Anh Lâm chúc tất cả các bạn nữ trong server luôn vui vẻ, xinh đẹp, hạnh phúc và code luôn bug-free nhá! =))
```cpp
(Tin nhắn tự động từ hệ thống bot)
```
        """
        
        for guild in bot.guilds:
            kênh_đích = None
            
            if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
                kênh_đích = guild.system_channel
            else:
                # Nếu không có, tìm kênh text đầu tiên chat được
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        kênh_đích = channel
                        break
            
            if kênh_đích:
                try:
                    await kênh_đích.send(loi_chuc)
                    await asyncio.sleep(1) # Nghỉ 1s để chống bị Discord phạt spam
                except Exception as e:
                    print(f"Lỗi gửi ở server {guild.name}: {e}")

@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập thành công với tên {bot.user}')
    if not tu_dong_chuc_8_3.is_running():
        tu_dong_chuc_8_3.start()
        print("⏰ Đã bật chế độ tự động canh đúng 18h ngày 8/3 để gửi lời chúc!")
    

@bot.command()
async def noitu(ctx, *, word: str):
    global noitu_games, used
    channel_id = ctx.channel.id
    
    word = word.strip().lower()
    words_split = word.split()

    # 1. Check luật cơ bản
    if len(words_split) != 2:
        await ctx.send("Sai luật rồi em ơi! Từ đưa ra phải có đúng 2 tiếng nhá. Đừng có lươn =))")
        return

    if len(vietnamese_dict) > 0 and word not in vietnamese_dict:
        await ctx.send(f"Cái từ `{word}` em rặn ở đâu ra đấy? Làm gì có trong từ điển tiếng Việt! Ngu ngốc, em thua rồi =))")
        if channel_id in noitu_games:
            del noitu_games[channel_id]
        return

    last_word = noitu_games.get(channel_id)

    if last_word:
        last_syllable = last_word.split()[-1]
        first_syllable = words_split[0]
        if first_syllable != last_syllable:
            await ctx.send(f"Mù mắt à =)) Phải bắt đầu bằng chữ `{last_syllable}` chứ. Khôn như em quê anh đầy!")
            return

    # 2. Tìm từ phản hồi của bot
    last_syllable_user = words_split[-1]
    valid_next_words = [w for w in vietnamese_dict if w.startswith(last_syllable_user + " ")]
    
    if not valid_next_words:
        await ctx.send(f"Chết tiệt, chữ `{last_syllable_user}` hiểm thế! Anh mày lật nát cuốn từ điển không ra chữ nào. Thôi ván này anh nhường, em thắng! :>>")
        if channel_id in noitu_games:
            del noitu_games[channel_id]
        used = set()
        return
    
    bot_word = random.choice(valid_next_words)
    ok = 0
    ind = 0
    while bot_word in used:
        bot_word = random.choice(valid_next_words)
        ind += 1
        if ind >= 20: 
            ok = 1
            break 
            
    if ok == 1:
        await ctx.send(f"Chết tiệt, chữ `{last_syllable_user}` hiểm thế! Anh mày lật nát cuốn từ điển không ra chữ nào. Thôi ván này anh nhường, em thắng! :>>")
        if channel_id in noitu_games:
            del noitu_games[channel_id]
        used = set()
        return
        
    # 3. Lưu dữ liệu ván đấu
    noitu_games[channel_id] = bot_word
    used.add(bot_word)
    used.add(word)
    
    # 4. Tra nghĩa của cả 2 từ (Dùng asyncio.to_thread để bot không bị đơ khi đợi mạng)
    nghia_user = await asyncio.to_thread(lay_nghia_tu, word)
    nghia_bot = await asyncio.to_thread(lay_nghia_tu, bot_word)
    
    # 5. Xuất kết quả
    msg = (
        f"✅ Em ra từ: **{word.capitalize()}**\n"
        f"> *📖 {nghia_user}*\n\n"
        f"🔥 Anh Lâm đáp trả: **{bot_word.capitalize()}**\n"
        f"> *📖 {nghia_bot}*\n\n"
        f"Nối tiếp chữ `{bot_word.split()[-1]}` đi em trai, dăm ba cái trò trẻ con :>>"
    )
    
    await ctx.send(msg)

@bot.command()
async def stopnoitu(ctx):
    global noitu_games
    if ctx.channel.id in noitu_games:
        del noitu_games[ctx.channel.id]
        await ctx.send("Đã dừng ván nối từ hiện tại. Bạn có thể bắt đầu ván mới!")
    else:
        await ctx.send("Hiện tại không có ván nối từ nào đang diễn ra.")
   
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
        
        # Đoạn code chia nhỏ tin nhắn dài
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
        
@bot.command()
async def guide(ctx):
    await ctx.send("""Tạo tài khoản với lệnh **>regis** và được cấp 100 dwc (đô la bò)
Check tiền còn lại với lệnh **>coin**
Chọn Xỉu (số lẻ) với lệnh **>xiu**
Chọn Tài (số chẵn) với lệnh **>tai**
Hết tiền thì xin anh Lâm chứ cũng không biết làm sao:>>>>""")

@bot.command()
async def regis(ctx):
    # db.exists kiểm tra xem user đã có trong database chưa
    if db.exists(ctx.author.name):
        await ctx.send(f"Đã có tài khoản **{ctx.author.name}**")
    else:
        # Lưu vào db: db.set(key, value)
        db.set(ctx.author.name, 100)
        await ctx.send(f"Đã tạo tài khoản {ctx.author.mention} với số tiền 100 dwc (đô la bò).")
    
@bot.command()
async def coin(ctx):
    # Lấy tiền từ db ra
    tien = db.get(ctx.author.name)
    if tien is not None: 
        await ctx.send(f"Số tiền của {ctx.author.mention} là: **{tien}** dwc")
    else:
        await ctx.send("Hãy tạo tài khoản với lệnh >regis")
    
@bot.command()
async def tai(ctx, tiencuoc=10):
    tien_hien_tai = db.get(ctx.author.name)
    
    if tien_hien_tai is None:
        await ctx.send("Hãy tạo tài khoản với lệnh >regis")
        return
        
    tien_hien_tai = int(tien_hien_tai) # Chuyển thành số nguyên để tính toán
    
    try:
        tiencuoc = int(tiencuoc)
        if tiencuoc > tien_hien_tai:
            await ctx.send("Tiền cược vượt quá số tiền hiện có. Mặc định all in!!!")
            tiencuoc = tien_hien_tai
    except ValueError:
        await ctx.send("Sai cú pháp rồi baby! >tai 10 nhé")
        return
        
    d1, d2, d3, total, ket_qua = lac_xuc_xac()
    
    await ctx.send(f"🎲 Xúc xắc đang lăn...")
    await asyncio.sleep(2) # Nên dùng asyncio.sleep thay vì time.sleep để bot không bị đơ
    await ctx.send(f"Kết quả: **{d1} - {d2} - {d3}** (Tổng: {total})\nAnh Lâm ra: **{ket_qua}**")
    
    if ket_qua == "Tài":
        tien_moi = tien_hien_tai + tiencuoc
        db.set(ctx.author.name, tien_moi) # Cập nhật lại db
        await ctx.send(f"🎉 Chúc mừng, {ctx.author.mention} chọn Tài và đã thắng! :>>\nSố tiền bạn có đã tăng lên {tien_moi} dwc!")
    else:
        tien_moi = tien_hien_tai - tiencuoc
        db.set(ctx.author.name, tien_moi) # Cập nhật lại db
        await ctx.send(f"💸 Tiếc quá, {ctx.author.mention} thua rồi. Còn thở là còn gỡ =))\nSố tiền bạn có đã giảm đi {tiencuoc} dwc và còn lại {tien_moi} dwc trong tài khoản!")

@bot.command()
async def xiu(ctx, tiencuoc=10):
    tien_hien_tai = db.get(ctx.author.name)
    
    if tien_hien_tai is None:
        await ctx.send("Hãy tạo tài khoản với lệnh >regis")
        return
        
    tien_hien_tai = int(tien_hien_tai) # Chuyển thành số nguyên để tính toán
    
    try:
        tiencuoc = int(tiencuoc)
        if tiencuoc > tien_hien_tai:
            await ctx.send("Tiền cược vượt quá số tiền hiện có. Mặc định all in!!!")
            tiencuoc = tien_hien_tai
    except ValueError:
        await ctx.send("Sai cú pháp rồi baby! >xiu 10 nhé")
        return
        
    d1, d2, d3, total, ket_qua = lac_xuc_xac()
    
    await ctx.send(f"🎲 Xúc xắc đang lăn...")
    await asyncio.sleep(2) # Nên dùng asyncio.sleep thay vì time.sleep để bot không bị đơ
    await ctx.send(f"Kết quả: **{d1} - {d2} - {d3}** (Tổng: {total})\nAnh Lâm ra: **{ket_qua}**")
    
    if ket_qua == "Xỉu":
        tien_moi = tien_hien_tai + tiencuoc
        db.set(ctx.author.name, tien_moi) # Cập nhật lại db
        await ctx.send(f"🎉 Chúc mừng, {ctx.author.mention} chọn Xỉu và đã thắng! :>>\nSố tiền bạn có đã tăng lên {tien_moi} dwc!")
    else:
        tien_moi = tien_hien_tai - tiencuoc
        db.set(ctx.author.name, tien_moi) # Cập nhật lại db
        await ctx.send(f"💸 Tiếc quá, {ctx.author.mention} thua rồi. Còn thở là còn gỡ =))\nSố tiền bạn có đã giảm đi {tiencuoc} dwc và còn lại {tien_moi} dwc trong tài khoản!")
        
bot.run(DISCORD_TOKEN)
