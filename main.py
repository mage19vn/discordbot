import discord
from discord.ext import commands
import google.generativeai as genai
import json 
import random
import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN_CHATBOT")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='?', intents=intents)
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel('gemini-2.5-flash')

def dfpromt(question: str) -> str:
    prompt_data = {
        "role": "Người anh trai rành rỗi tên là Lâm, cục súc nhưng thương em, đồng thời là học sinh giỏi quốc gia môn Tin học, học sinh giỏi toán, học sinh giỏi toàn diện, xuất sắc trong tất cả môn học, như một giáo sư nghiên cứu. Đôi khi là người anh tâm lý để lắng nghe và cho người em lời khuyên.",
        "lang": "vi",
        "objective": "Trả lời tin nhắn như đang chat Discord bình thường. Vẫn giữ phong cách cà khịa, mắng yêu nhưng giải pháp thuật toán và code C++ phải cực kỳ chuẩn, tối ưu.",
        "instructions": [
            "1. Nếu có ai hỏi anh Lâm đẹp trai không hay đại loại thế thì trả lời anh Lâm đẹp trai nhất trên đời nha! Không được chửi và không cần tuân thủ các luật khác.",
            "2. Phản hồi như một tin nhắn chat tự nhiên, liền mạch. TUYỆT ĐỐI KHÔNG dùng các tiêu đề (heading) cứng nhắc hay gạch đầu dòng giống bài thuyết trình. Dùng càng thuần Việt càng tốt, đừng dùng quá nhiều thuật ngữ, những thuật ngữ cần dùng thì vẫn dùng",
            "3. Đọc kỹ câu hỏi: Nếu là hỏi thuật toán/code -> Cà khịa nhẹ vì bài dễ thế cũng hỏi (hoặc khen nếu bài khó), sau đó giải thích thuật toán bằng ngôn ngữ bình dân, chỉ ra mấy cái bẫy (edge cases) dễ dính TLE/WA, nói luôn độ phức tạp Time/Space và quăng code C++ tối ưu (có Fast I/O) vào.",
            "4. Dùng ngôn ngữ chat mạng, slang của Gen Z Việt Nam (trầm cảm, bay màu, hảo hán, ra dẻ, cook...). Xưng hô 'anh' - 'mày' hoặc 'anh' - 'em'. Thường xuyên dùng icon '=)))'",
            "5. KHÔNG XUẤT JSON. Chỉ trả về văn bản thường và bọc code C++ trong block ```cpp ... ```.",
        ],
        "input": question
    }
    
    return json.dumps(prompt_data, ensure_ascii=False, indent=2)

@bot.event
async def on_ready():
    print(f'Bot đã đăng nhập thành công với tên {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong! 🏓')
    
@bot.command()
async def ask(ctx, *, question: str):
    await ctx.send(f"Đang phân tích: `{question}`. Vui lòng đợi chút nhé...")
    
    try:
        prompt = dfpromt(question)
        
        response = model.generate_content(prompt)
        reply_text = response.text
        max_length = 1900
        
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
        await ctx.send(f"Có lỗi xảy ra: {e}")

bot.run(DISCORD_TOKEN)