"""Central administrator and input policy shared by both adapters."""

import os

MAX_CODE_BYTES = 64 * 1024
MAX_INPUT_BYTES = 64 * 1024


def _ids(name):
    return {value.strip() for value in os.getenv(name, "").split(",") if value.strip()}


def discord_admin(user):
    return str(user.id) in _ids("DISCORD_ADMIN_IDS")


def telegram_admin(user):
    return str(user.id) in _ids("TELEGRAM_ADMIN_IDS")


def admin_id(platform, user_id):
    name = {"telegram": "TELEGRAM_ADMIN_IDS", "discord": "DISCORD_ADMIN_IDS"}.get(platform)
    return bool(name and str(user_id) in _ids(name))


def valid_code(code):
    return bool(code.strip()) and len(code.encode("utf-8")) <= MAX_CODE_BYTES


def valid_input(value):
    return len(value.encode("utf-8")) <= MAX_INPUT_BYTES
