"""Check the C++ toolchain without connecting to bot APIs or touching the DB."""

from pathlib import Path
import subprocess
import tempfile

from sandbox import BACKEND, SandboxUnavailable, run_compiler, run_program


def check_runner():
    try:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            if BACKEND == "docker":
                root.chmod(0o777)
            source, program = root / "check.cpp", root / "check"
            source.write_text('#include<iostream>\nint main(){int n;std::cin>>n;std::cout<<n*2;}', encoding="utf-8")
            source.chmod(0o644)
            result = run_compiler(source, program, timeout=30)
            if result.returncode:
                return False, "Biên dịch thất bại: " + result.stderr[:1500]
            result = run_program(program, "21\n", timeout=2)
            if result.returncode or result.stdout.strip() != "42":
                return False, "Chạy C++ thất bại: " + result.stderr[:1500]
    except (OSError, SandboxUnavailable) as exc:
        return False, f"Trình chạy chưa sẵn sàng ({type(exc).__name__}). Kiểm tra Linux, g++ và resource limits."
    except (TimeoutError, subprocess.TimeoutExpired):
        return False, "Trình kiểm tra chạy quá thời gian."
    return True, "C++ OK: biên dịch và chạy 21 → 42 với giới hạn tài nguyên."
