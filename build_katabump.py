"""Build a panel-ready ZIP without credentials, live data or local binaries."""

from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = (
    "main.py", "bootstrap.py", "paths.py", "config.py", "access.py", "core.py",
    "storage.py", "sandbox.py", "limit_exec.py", "healthcheck.py", "bot_discord.py",
    "bot_telegram.py", "bot_zalo.py", "zalo_games.py", "zalo_ui.py", "problem_import.py",
    "requirements.txt", ".env.example", "README.md", "KATABUMP.md", "ZALO_GAME_GUIDE.md",
    "submit.html", "examples/problem.json",
)


def build(output=None):
    output = Path(output) if output else ROOT / "dist" / "magoj-katabump.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / name for name in FILES]
    for folder in sorted(ROOT.glob("zalo.*")):
        if folder.is_dir() and not folder.is_symlink():
            paths.extend(path for path in sorted(folder.iterdir())
                         if path.is_file() and not path.is_symlink() and
                         (path.suffix == ".py" or path.name in ("der.json", "README.md")))
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or linked deployment file: {path.name}")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ROOT).as_posix())
        # The root data.json on the host takes priority; never overwrite it.
        archive.write(ROOT / "data.json", "examples/seed-data.json")
    return output


if __name__ == "__main__":
    result = build()
    print(f"Đã tạo {result.name} ({result.stat().st_size // 1024} KiB) trong dist/.")
