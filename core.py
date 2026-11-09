import asyncio
import os
import random
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import storage
import access
from sandbox import BACKEND, SandboxUnavailable, run_compiler, run_program

NUM_TESTS = 10
TIMEOUT = 2
COMPILE_TIMEOUT = 30  # giây, cho mỗi lần gọi g++
_judge_slots = asyncio.Semaphore(max(1, int(os.getenv("MAGOJ_MAX_JOBS") or "1")))
storage.initialize()

_photo_slots = asyncio.Semaphore(1)
MAX_MARKDOWN_BYTES = 64 * 1024
MAX_PHOTO_HEIGHT = 12000


class PhotoRenderError(RuntimeError):
    """An image cannot be rendered or published with the current configuration."""


def markdown_to_html(markdown: str) -> str:
    """Render untrusted Markdown without raw HTML, scripts or remote images."""
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("Markdown không được để trống.")
    if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise ValueError("Markdown vượt quá 64 KiB.")
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise PhotoRenderError("Thiếu markdown-it-py; cài requirements.txt.") from exc
    body = (MarkdownIt("commonmark", {"html": False, "breaks": True})
            .enable("table").disable("image").render(markdown))
    return """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<style>
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: #172033;
       font: 20px/1.6 Arial, 'Noto Sans', sans-serif; }
main { padding: 32px; overflow-wrap: anywhere; }
h1,h2,h3 { line-height: 1.3; color: #183b65; }
pre { white-space: pre-wrap; padding: 16px; background: #f1f4f8; border-radius: 8px; }
code { font-family: Consolas, 'DejaVu Sans Mono', monospace; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th,td { border: 1px solid #cad3df; padding: 10px; text-align: left; }
th { background: #edf2f8; }
blockquote { margin-left: 0; padding-left: 16px; border-left: 4px solid #527eb0; }
a { color: #185fa5; }
</style></head><body><main>""" + body + "</main></body></html>"


async def markdown_to_png(markdown: str, *, width: int = 960) -> bytes:
    """Markdown -> self-contained HTML -> PNG. No files or network requests."""
    if not isinstance(width, int) or not 480 <= width <= 1600:
        raise ValueError("Chiều rộng ảnh phải từ 480 đến 1600 pixel.")
    html = markdown_to_html(markdown)
    try:
        from playwright.async_api import async_playwright, Error as PlaywrightError
    except ImportError as exc:
        raise PhotoRenderError("Thiếu playwright; cài requirements.txt và chạy "
                               "python -m playwright install chromium --only-shell.") from exc

    async def capture():
        async with async_playwright() as engine:
            browser = await engine.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width": width, "height": 720},
                                              device_scale_factor=1, java_script_enabled=False)
                await page.route("**/*", lambda route: route.abort())
                await page.set_content(html, wait_until="load", timeout=10000)
                content = page.locator("main")
                bounds = await content.bounding_box()
                if bounds is None or bounds["height"] > MAX_PHOTO_HEIGHT:
                    raise ValueError("Nội dung quá dài cho một ảnh; hãy chia nhỏ Markdown.")
                return await content.screenshot(type="png", timeout=10000,
                                                animations="disabled")
            finally:
                await browser.close()

    async with _photo_slots:
        try:
            return await asyncio.wait_for(capture(), timeout=30)
        except (PlaywrightError, asyncio.TimeoutError) as exc:
            raise PhotoRenderError("Không chụp được PNG. Cài Chromium bằng python -m playwright "
                                   "install chromium --only-shell; kiểm tra thư viện hệ thống "
                                   "và RAM của hosting.") from exc


def _photo_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
        raise PhotoRenderError("Cần URL HTTPS công khai để Zalo tải ảnh.")
    return value.rstrip("/")


async def save_png(png: bytes) -> Path:
    """Persist a complete PNG under a unique name in MAGOJ_PHOTO_DIR."""
    from paths import project_path
    directory = project_path(os.getenv("MAGOJ_PHOTO_DIR") or "generated_photos")
    name = uuid4().hex + ".png"

    def save():
        directory.mkdir(parents=True, exist_ok=True)
        # Publish only complete images, including when a web server reads concurrently.
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(png)
            except BaseException:
                stream.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(directory / name)
        finally:
            temporary.unlink(missing_ok=True)

    await asyncio.to_thread(save)
    return directory / name


async def upload_png_cloudinary(path: Path) -> str:
    """Upload a saved PNG with signed server-side credentials; return its HTTPS URL."""
    names = ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    values = [os.getenv(name, "").strip() for name in names]
    missing = [name for name, value in zip(names, values) if not value]
    if missing:
        raise PhotoRenderError("Thiếu cấu hình Cloudinary: " + ", ".join(missing) +
                               ". PNG đã được giữ trong thư mục ảnh.")
    try:
        from cloudinary.uploader import upload
    except ImportError:
        raise PhotoRenderError("Thiếu cloudinary; cài requirements.txt. PNG đã được lưu.") from None
    folder = (os.getenv("CLOUDINARY_FOLDER") or "magoj").strip("/") or "magoj"
    try:
        result = await asyncio.to_thread(
            upload, str(path), cloud_name=values[0], api_key=values[1], api_secret=values[2],
            resource_type="image", type="upload", public_id=f"{folder}/{path.stem}",
            overwrite=False, timeout=30,
        )
        return _photo_base_url(result["secure_url"])
    except Exception:
        # SDK/network error details may contain credentials. Keep them out of chat/logs.
        raise PhotoRenderError("Không upload được ảnh lên Cloudinary. Kiểm tra API keys, "
                               "kết nối và hạn mức tài khoản. PNG vẫn được giữ trên máy.") from None


async def publish_png(png: bytes) -> str:
    """Save locally, then upload to Cloudinary or use an existing static server.

    Files are retained when credentials, uploading or sending fail. With no
    explicit provider, Cloudinary credentials select Cloudinary; otherwise local.
    """
    path = await save_png(png)
    cloudinary_configured = any(os.getenv(name, "").strip() for name in
                                ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"))
    provider = (os.getenv("MAGOJ_PHOTO_PROVIDER") or
                ("cloudinary" if cloudinary_configured else "local")).strip().lower()
    if provider == "cloudinary":
        return await upload_png_cloudinary(path)
    if provider != "local":
        raise PhotoRenderError("MAGOJ_PHOTO_PROVIDER phải là cloudinary hoặc local. PNG đã được lưu.")
    try:
        base = _photo_base_url(os.getenv("MAGOJ_PHOTO_BASE_URL", ""))
    except PhotoRenderError as exc:
        raise PhotoRenderError(f"Đã lưu PNG: {path.name}. Chưa gửi được: cần cấu hình "
                               "MAGOJ_PHOTO_BASE_URL trỏ đến thư mục ảnh qua HTTPS.") from exc
    name = path.name
    return f"{base}/{name}"


async def send_markdown_photo(bot, chat_id: str, markdown: str, *,
                              caption: str = "Ảnh từ Markdown", publish=None,
                              width: int = 960):
    """Render and send through Zalo SDK send_photo (Bot API sendPhoto).

    Optional ``publish`` is an async callable: PNG bytes -> public HTTPS URL.
    It can upload to your own storage instead of the default static directory.
    Returns the SDK Message; render, storage and API errors propagate to the caller.
    """
    if not isinstance(caption, str) or not 1 <= len(caption) <= 2000:
        raise ValueError("Caption phải có từ 1 đến 2000 ký tự.")
    if publish is None:
        publish = publish_png
    png = await markdown_to_png(markdown, width=width)
    url = _photo_base_url(await publish(png))
    return await bot.send_photo(chat_id=str(chat_id), photo=url, caption=caption)


def strip_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```") and code.endswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1]) if len(lines) >= 2 else code.strip("`")
    return code.replace("```cpp\n", "").replace("```", "")


def create_problem(name: str, author=None) -> bool:
    return storage.create_problem(name, author)


def set_problem_field(name: str, field: str, code: str) -> bool:
    return storage.set_field(name, field, code)


def get_problem(name: str):
    return storage.get_problem(name)


def visible_problem(name, platform, user_id):
    problem = get_problem(name)
    if problem and (problem.get("published", True) or access.admin_id(platform, user_id)):
        return problem
    return None


def list_problems() -> dict:
    return storage.list_problems()


def list_visible_problems(platform, user_id):
    cats = {}
    for category, names in list_problems().items():
        for name in names:
            if visible_problem(name, platform, user_id):
                cats.setdefault(category, []).append(name)
    return cats


def set_category(name: str, cat: str) -> bool:
    return storage.set_field(name, "category", cat)


def set_user_input(user_id: str, inp: str):
    storage.set_input(user_id, inp)


def get_user_input(user_id: str) -> str:
    return storage.get_input(user_id)


def add_fixed_test(name: str, value: str):
    if not value.strip() or len(value.encode("utf-8")) > 4096:
        return "invalid"
    return storage.append_fixed_test(name, value)


def set_limits(name: str, test_count: int, time_limit: int, memory_limit: int):
    if not (1 <= test_count <= 10 and 1 <= time_limit <= 2 and 64 <= memory_limit <= 128):
        return False
    if get_problem(name) is None:
        return False
    return storage.set_fields(name, {"test_count": test_count,
                                     "time_limit": time_limit,
                                     "memory_limit": memory_limit})


async def is_ac(inp: str, sol: str, out: str, checker_exe: str,
                timeout=TIMEOUT, memory=128) -> bool:
    if not checker_exe:
        return sol.strip() == out.strip()
    check = inp + "\nENDINP\n" + sol + "\nENDOUT\n" + out
    try:
        proc = await asyncio.to_thread(
            run_program, checker_exe, check, timeout, memory=memory,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "AC"
    except subprocess.TimeoutExpired:
        return False


async def _compile(src: str, exe: str):
    """Biên dịch bằng g++. Trả về CompletedProcess, hoặc None nếu máy chưa cài g++.
    Hết thời gian thì giả lập lỗi biên dịch để caller báo CE như thường."""
    try:
        return await asyncio.to_thread(
            run_compiler, src, exe, COMPILE_TIMEOUT,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["g++"], returncode=1, stdout="",
            stderr=f"Biên dịch quá thời gian cho phép ({COMPILE_TIMEOUT}s).",
        )


async def _run(exe: str, inp: str, timeout=TIMEOUT, memory=128):
    return await asyncio.to_thread(
        run_program, exe, inp, timeout, memory=memory,
    )


async def judge(name: str, code: str, platform=None, user_id=None):
    if not access.valid_code(code):
        yield {"t": "sys", "msg": "code_limit"}
        return
    try:
        await asyncio.wait_for(_judge_slots.acquire(), timeout=3)
    except asyncio.TimeoutError:
        yield {"t": "sys", "msg": "busy"}
        return
    seed = random.SystemRandom().randrange(1, 2**62)
    held = True
    try:
        try:
            async for event in _judge_unqueued(name, code, seed, platform, user_id):
                if event["t"] not in ("status", "not_found"):
                    event["seed"] = seed
                if event["t"] != "status":
                    if platform and user_id is not None and event["t"] != "not_found":
                        storage.record_submission(platform, user_id, name, event["t"], seed, event)
                    _judge_slots.release()
                    held = False
                yield event
        except SandboxUnavailable:
            if platform and user_id is not None:
                storage.record_submission(platform, user_id, name, "sys", seed)
            _judge_slots.release()
            held = False
            yield {"t": "sys", "msg": "sandbox", "seed": seed}
    finally:
        if held:
            _judge_slots.release()


async def _judge_unqueued(name: str, code: str, seed: int, platform=None, user_id=None):
    p = visible_problem(name, platform, user_id)
    if p is None:
        yield {"t": "not_found"}
        return

    test_count = p.get("test_count", NUM_TESTS)
    timeout = p.get("time_limit", TIMEOUT)
    memory = p.get("memory_limit", 128)
    fixed_tests = p.get("fixed_tests", [])[:test_count]
    yield {"t": "status", "msg": "compiling", "count": test_count}

    with tempfile.TemporaryDirectory() as d:
        if BACKEND == "docker":
            os.chmod(d, 0o777)  # container user needs access to its only mounted directory
        cpp, sol_f, gen_f = (os.path.join(d, n) for n in ("temp.cpp", "solution.cpp", "gen_test.cpp"))
        exe, exe_sol, exe_gen = (os.path.join(d, n) for n in ("temp", "solution", "gen_test"))
        for path, content in ((cpp, code), (sol_f, p["solution"]), (gen_f, p["gen_test"])):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            if BACKEND == "docker":
                os.chmod(path, 0o644)

        checker_exe = ""
        if p["checker"]:
            chk_f = os.path.join(d, "checker.cpp")
            checker_exe = os.path.join(d, "checker")
            with open(chk_f, "w", encoding="utf-8") as f:
                f.write(p["checker"])
            if BACKEND == "docker":
                os.chmod(chk_f, 0o644)
            r = await _compile(chk_f, checker_exe)
            if r is None:
                yield {"t": "sys", "msg": "no_compiler"}
                return
            if r.returncode != 0:
                yield {"t": "ce", "who": "checker", "stderr": r.stderr}
                return

        r = await _compile(cpp, exe)
        if r is None:
            yield {"t": "sys", "msg": "no_compiler"}
            return
        if r.returncode != 0:
            yield {"t": "ce", "who": "user", "stderr": r.stderr}
            return
        r = await _compile(sol_f, exe_sol)
        if r is None:
            yield {"t": "sys", "msg": "no_compiler"}
            return
        if r.returncode != 0:
            yield {"t": "ce", "who": "solution", "stderr": r.stderr}
            return
        if len(fixed_tests) < test_count:
            if not p["gen_test"].strip():
                yield {"t": "sys", "msg": "gen_missing"}
                return
            r = await _compile(gen_f, exe_gen)
            if r is None:
                yield {"t": "sys", "msg": "no_compiler"}
                return
            if r.returncode != 0:
                yield {"t": "ce", "who": "gen", "stderr": r.stderr}
                return

        yield {"t": "status", "msg": "testing", "count": test_count}

        for i in range(1, test_count + 1):
            if i <= len(fixed_tests):
                inp = fixed_tests[i - 1]
            else:
                try:
                    g = await asyncio.to_thread(run_program, exe_gen, "", timeout,
                                                seed + i, memory)
                except subprocess.TimeoutExpired:
                    yield {"t": "sys", "msg": "gen_tle"}
                    return
                if g.returncode != 0:
                    yield {"t": "sys", "msg": "gen_rte", "detail": g.stderr}
                    return
                inp = g.stdout
            if inp.strip() == "":
                yield {"t": "sys", "msg": "gen_empty"}
                return

            try:
                s = await _run(exe_sol, inp, timeout, memory)
            except subprocess.TimeoutExpired:
                yield {"t": "sys", "msg": "sol_tle"}
                return
            if s.returncode != 0:
                yield {"t": "sys", "msg": "sol_rte", "detail": s.stderr}
                return

            try:
                u = await _run(exe, inp, timeout, memory)
            except subprocess.TimeoutExpired:
                yield {"t": "tle", "test": i, "limit": timeout}
                return
            if u.returncode != 0 or u.stderr != "":
                yield {"t": "rte", "test": i, "stderr": u.stderr}
                return
            if not await is_ac(inp, s.stdout, u.stdout, checker_exe, timeout, memory):
                yield {"t": "wa", "test": i,
                       "inp": inp, "sol": s.stdout, "out": u.stdout}
                return

        yield {"t": "ac", "count": test_count}


async def run_once(code: str, inp: str):
    if not access.valid_code(code) or not access.valid_input(inp):
        return {"t": "sys", "msg": "code_limit"}
    try:
        await asyncio.wait_for(_judge_slots.acquire(), timeout=3)
    except asyncio.TimeoutError:
        return {"t": "sys", "msg": "busy"}
    try:
        return await _run_once_unqueued(code, inp)
    finally:
        _judge_slots.release()


async def _run_once_unqueued(code: str, inp: str):
    with tempfile.TemporaryDirectory() as d:
        if BACKEND == "docker":
            os.chmod(d, 0o777)
        cpp = os.path.join(d, "temp.cpp")
        exe = os.path.join(d, "temp")
        with open(cpp, "w", encoding="utf-8") as f:
            f.write(code)
        if BACKEND == "docker":
            os.chmod(cpp, 0o644)
        try:
            r = await _compile(cpp, exe)
        except SandboxUnavailable:
            return {"t": "sys", "msg": "sandbox"}
        if r is None:
            return {"t": "ce", "stderr": "Máy chấm chưa cài g++, không biên dịch được. Báo admin cài giúp nhé!"}
        if r.returncode != 0:
            return {"t": "ce", "stderr": r.stderr}
        try:
            u = await _run(exe, inp)
        except subprocess.TimeoutExpired:
            return {"t": "tle"}
        except SandboxUnavailable:
            return {"t": "sys", "msg": "sandbox"}
        if u.returncode != 0:
            return {"t": "rte", "stderr": u.stderr}
        if u.stdout == "" and u.stderr == "":
            return {"t": "empty"}
        return {"t": "ok", "output": u.stdout[:1900],
                "truncated": len(u.stdout) > 1900}


SAMPLE_SOLUTION = """#include<bits/stdc++.h>
using namespace std;

int main() {
    int k;
    cin >> k;
    // Xu ly bai toan
    cout << k * 2 << "\\n";
}"""

SAMPLE_GEN = """#include<bits/stdc++.h>
using namespace std;

mt19937_64 rng([] {
    const char* seed = getenv("MAGOJ_SEED");
    return seed ? stoull(seed) : (unsigned long long)chrono::steady_clock::now().time_since_epoch().count();
}());

long long rand_int(long long L, long long R) {
    return uniform_int_distribution<long long>(L, R)(rng);
}

int main() {
    long long n = rand_int(1, 10);
    cout << n;
}"""

SAMPLE_CHECKER = """#include<bits/stdc++.h>
using namespace std;

int main() {
    vector<string> inp, magCode, student;
    string s;
    int state = 0;
    while (cin >> s) {
        if (s == "ENDINP") { state = 1; continue; }
        if (s == "ENDOUT") { state = 2; continue; }
        if (state == 0) inp.push_back(s);
        else if (state == 1) magCode.push_back(s);
        else student.push_back(s);
    }

    sort(magCode.begin(), magCode.end());
    sort(student.begin(), student.end());

    if (magCode == student) cout << "AC";
    else cout << "WA";
}"""
