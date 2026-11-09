"""Startup checks that report names and status, never credential values."""

import os
import shutil
import sys
from urllib.parse import urlsplit
from paths import project_path


def check_config():
    errors, warnings = [], []
    telegram = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    discord = bool(os.getenv("DISCORD_TOKEN", "").strip())
    zalo = bool(os.getenv("ZALO_BOT_TOKEN", "").strip())
    if not telegram and not discord and not zalo:
        errors.append("Cần TELEGRAM_BOT_TOKEN, DISCORD_TOKEN hoặc ZALO_BOT_TOKEN.")
    for name in ("TELEGRAM_ADMIN_IDS", "DISCORD_ADMIN_IDS"):
        values = [part.strip() for part in os.getenv(name, "").split(",") if part.strip()]
        if any(not item.isdecimal() for item in values):
            errors.append(f"{name} phải là ID số, ngăn bằng dấu phẩy.")
    if telegram and not os.getenv("TELEGRAM_ADMIN_IDS", "").strip():
        warnings.append("TELEGRAM_ADMIN_IDS trống: lệnh quản trị Telegram bị khóa.")
    if discord and not os.getenv("DISCORD_ADMIN_IDS", "").strip():
        warnings.append("DISCORD_ADMIN_IDS trống: lệnh quản trị Discord bị khóa.")
    if zalo and not os.getenv("ZALO_ADMIN_IDS", "").strip():
        warnings.append("ZALO_ADMIN_IDS trống: lệnh quản trị Zalo bị khóa.")
    webapp = os.getenv("MAGOJ_WEBAPP_URL", "").strip()
    if webapp:
        try:
            url = urlsplit(webapp)
            valid = (url.scheme == "https" and bool(url.netloc)
                     and not url.username and not url.password)
        except ValueError:
            valid = False
        if not valid:
            errors.append("MAGOJ_WEBAPP_URL phải là URL HTTPS công khai.")
    try:
        if int(os.getenv("MAGOJ_MAX_JOBS") or "1") < 1:
            raise ValueError
    except ValueError:
        errors.append("MAGOJ_MAX_JOBS phải là số nguyên dương.")
    backend = (os.getenv("MAGOJ_JUDGE_BACKEND") or "local").lower()
    if backend == "local":
        if sys.platform == "win32":
            warnings.append("Trình chạy C++ local cần POSIX resource limits; trên Windows hãy dùng máy chấm Linux.")
        if not shutil.which("g++"):
            warnings.append("Không tìm thấy g++: bot/game vẫn chạy, nhưng lệnh chạy/nộp C++ chưa dùng được. Chọn image có GCC trên KataBump.")
    elif backend == "docker":
        if not shutil.which("docker"):
            errors.append("Chế độ Docker được chọn nhưng không tìm thấy docker.")
    else:
        errors.append("MAGOJ_JUDGE_BACKEND phải là local hoặc docker.")
    path = project_path(os.getenv("MAGOJ_DB_PATH") or "data.sqlite3").parent
    ancestor = path
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    if not os.access(ancestor, os.W_OK):
        errors.append("Thư mục chứa database không có quyền ghi.")
    return errors, warnings
