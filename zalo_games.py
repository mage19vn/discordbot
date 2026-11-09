"""Load trusted Zalo game commands from local ``zalo.*`` folders."""

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import re
import sys
from typing import Callable


LOG = logging.getLogger(__name__)
COMMAND_RE = re.compile(r"^[a-z_][a-z_0-9]*$")
HANDLER_RE = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)\.py:([A-Za-z_][A-Za-z_0-9]*)$")


@dataclass(frozen=True)
class GameCommand:
    game: str
    description: str
    handler: Callable
    title: str = ""
    help: str = ""


@dataclass
class GameContext:
    """Data passed to a game function for one command invocation."""

    chat_id: str
    user_id: str
    args: str
    state: dict
    send: Callable
    display_name: str = ""

    async def reply(self, text: str) -> None:
        await self.send(self.chat_id, text)


def load_games(root: Path, reserved: set[str]) -> dict[str, GameCommand]:
    """Load each game once at startup; a bad folder does not stop other games."""

    commands: dict[str, GameCommand] = {}
    if not root.is_dir():
        return commands
    for folder in sorted(root.iterdir()):
        if not folder.name.startswith("zalo.") or len(folder.name) <= 5 or not folder.is_dir() or folder.is_symlink():
            continue
        loaded_names = []
        try:
            manifest_path = folder / "der.json"
            if manifest_path.is_symlink():
                raise ValueError("der.json không được là symlink")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or not isinstance(manifest.get("commands"), dict):
                raise ValueError("der.json phải có object 'commands'")
            if not manifest["commands"]:
                raise ValueError("commands không được rỗng")
            title = manifest.get("title", folder.name[5:])
            help_text = manifest.get("help", "")
            if not isinstance(title, str) or not isinstance(help_text, str):
                raise ValueError("title và help phải là chuỗi")
            modules = {}
            pending = {}
            for name, definition in manifest["commands"].items():
                if not isinstance(name, str) or not COMMAND_RE.fullmatch(name):
                    raise ValueError(f"tên lệnh không hợp lệ: {name!r}")
                if name in reserved or name in commands:
                    raise ValueError(f"lệnh /{name} đã tồn tại")
                if not isinstance(definition, dict):
                    raise ValueError(f"/{name} phải là object")
                description = definition.get("description")
                target = definition.get("handler")
                match = HANDLER_RE.fullmatch(target) if isinstance(target, str) else None
                if not isinstance(description, str) or not description.strip() or not match:
                    raise ValueError(f"/{name} cần description và handler dạng file.py:function")
                filename, function = match.groups()
                path = folder / f"{filename}.py"
                if not path.is_file() or path.is_symlink():
                    raise ValueError(f"không tìm thấy file Python cho /{name}: {path.name}")
                if filename not in modules:
                    module_name = "_zalo_game_" + hashlib.sha256(
                        str(path.resolve()).encode("utf-8")).hexdigest()[:20]
                    spec = importlib.util.spec_from_file_location(
                        module_name, path)
                    if spec is None or spec.loader is None:
                        raise ValueError(f"không nạp được {path.name}")
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    try:
                        spec.loader.exec_module(module)
                    except Exception:
                        sys.modules.pop(module_name, None)
                        raise
                    loaded_names.append(module_name)
                    modules[filename] = module
                handler = getattr(modules[filename], function, None)
                if not callable(handler):
                    raise ValueError(f"không tìm thấy hàm {function} trong {path.name}")
                pending[name] = GameCommand(folder.name, description.strip(), handler,
                                            title, help_text)
            commands.update(pending)
            LOG.info("Đã nạp game Zalo %s: %s", folder.name, ", ".join(pending))
        except Exception as exc:
            for module_name in loaded_names:
                sys.modules.pop(module_name, None)
            LOG.warning("Bỏ qua game Zalo %s: %s", folder.name, exc)
    return commands
