"""Dependency installation for hosting panels; standard library only."""

from importlib import metadata, util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
MODULES = {"discord.py": "discord", "python-telegram-bot": "telegram",
           "python-dotenv": "dotenv", "python-zalo-bot": "zalo_bot",
           "markdown-it-py": "markdown_it", "playwright": "playwright"}
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def ensure_pip():
    """Seed pip in the active interpreter, including venvs created without pip."""
    if util.find_spec("pip") is not None:
        return
    user = ["--user"] if sys.prefix == sys.base_prefix else []
    print("pip is missing; trying Python ensurepip...", flush=True)
    try:
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade", *user],
                       cwd=ROOT, check=True, timeout=120)
        subprocess.run([sys.executable, "-m", "pip", "--version"],
                       cwd=ROOT, check=True, capture_output=True, timeout=30)
        return
    except (OSError, subprocess.SubprocessError):
        # Minimal hosting images can omit ensurepip as well as pip.
        print("ensurepip unavailable; installing pip from bootstrap.pypa.io...", flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix="magoj-pip-") as folder:
            script = Path(folder) / "get-pip.py"
            with urlopen(GET_PIP_URL, timeout=30) as response:
                if not response.geturl().startswith("https://bootstrap.pypa.io/"):
                    raise OSError("Unexpected pip bootstrap redirect")
                limit = 4 * 1024 * 1024
                content = response.read(limit + 1)
                if not content or len(content) > limit:
                    raise OSError("Invalid pip bootstrap size")
                script.write_bytes(content)
            subprocess.run([sys.executable, str(script), "--disable-pip-version-check",
                            "--no-cache-dir", *user], cwd=ROOT, check=True, timeout=180)
            subprocess.run([sys.executable, "-m", "pip", "--version"],
                           cwd=ROOT, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise SystemExit("Không khởi tạo được pip trong Python hiện tại. Kiểm tra log phía trên, "
                         "quyền ghi .venv và kết nối bootstrap.pypa.io/PyPI; "
                         "chọn lại image Python 3.12 hoặc nhờ KataBump khôi phục pip cho .venv.") from None


def ensure_dependencies(install=True):
    if sys.version_info < (3, 10):
        raise SystemExit("MagOJ cần Python 3.10+. Chọn Python 3.12 trong Startup của KataBump.")
    requirements = ROOT / "requirements.txt"
    if not requirements.is_file():
        raise SystemExit("Thiếu requirements.txt. Upload file này cạnh main.py rồi Restart.")
    missing = []
    for line in requirements.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s#]+)", line)
        if not match:
            raise SystemExit("requirements.txt phải dùng các phiên bản được ghim bằng ==.")
        package, expected = match.groups()
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            installed = None
        module = MODULES.get(package)
        missing_extra = package == "python-telegram-bot" and util.find_spec("apscheduler") is None
        if installed != expected or (module and util.find_spec(module) is None) or missing_extra:
            missing.append(package)
    if not missing:
        return
    if os.getenv("MAGOJ_BOOTSTRAP_ATTEMPTED") == "1":
        raise SystemExit("Dependencies vẫn chưa dùng được sau khi cài. Kiểm tra pip/interpreter và "
                         "quyền thư mục .local; không tự cài lặp lại.")
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "--no-cache-dir", "-r", str(requirements)]
    if sys.prefix == sys.base_prefix:
        command.insert(4, "--user")
    if not install:
        raise SystemExit("Thiếu hoặc sai phiên bản: " + ", ".join(missing) +
                         ". Chạy python -m pip install -r requirements.txt rồi khởi động lại.")
    print("Installing dependencies: " + ", ".join(missing), flush=True)
    ensure_pip()
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit("Cài dependencies thất bại. Kiểm tra log pip phía trên và kết nối PyPI; "
                         "giữ requirements.txt ở gốc server rồi Restart.") from None
    # Start a fresh interpreter so a newly created user site is included in sys.path.
    os.environ["MAGOJ_BOOTSTRAP_ATTEMPTED"] = "1"
    os.execv(sys.executable, [sys.executable, str(ROOT / "main.py"), *sys.argv[1:]])
