"""Resource-limited local runner, with optional Docker isolation."""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

IMAGE = os.getenv("MAGOJ_JUDGE_IMAGE", "gcc@sha256:6f37e44a9b41181de5dd97366ec732652f5d895a72b5549c64694efed50a97e8")
BACKEND = (os.getenv("MAGOJ_JUDGE_BACKEND") or "local").lower()


class SandboxUnavailable(RuntimeError):
    pass


def _local(workdir, args, *, input_text=None, timeout=30, memory=256, seed=None,
           output_limit=131072):
    """Limit resource exhaustion. This does not isolate filesystem or network."""
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}
    if seed is not None:
        env["MAGOJ_SEED"] = str(seed)
    cmd = [sys.executable, str(Path(__file__).with_name("limit_exec.py")),
           str(timeout), str(memory * 1024 * 1024), str(output_limit), *args]
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(cmd, cwd=workdir, env=env, stdin=subprocess.PIPE,
                                    stdout=out, stderr=err, text=True,
                                    start_new_session=True)
            try:
                proc.communicate(input_text, timeout=timeout + 1)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                raise
            out.seek(0)
            err.seek(0)
            stdout = out.read(65536).decode("utf-8", errors="replace")
            stderr = err.read(65536).decode("utf-8", errors="replace")
        if proc.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
            raise subprocess.TimeoutExpired(cmd, timeout)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except FileNotFoundError as exc:
        raise SandboxUnavailable("local runner tool is missing") from exc


def _docker(workdir, args, *, input_text=None, timeout=30, memory="256m", seed=None):
    path = Path(workdir).resolve()
    name = "magoj-" + uuid.uuid4().hex
    cmd = ["docker", "run", "--rm", "-i", "--name", name,
           "--network", "none", "--read-only",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--pids-limit", "32", "--memory", memory, "--cpus", "1",
           "--user", "65534:65534", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
           "--mount", f"type=bind,src={path},dst=/work", "--workdir", "/work"]
    if seed is not None:
        cmd.extend(["--env", f"MAGOJ_SEED={seed}"])
    cmd.extend([IMAGE, *args])
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            result = subprocess.run(
                ["prlimit", "--fsize=131072:131072", "--", *cmd],
                input=input_text, text=True, stdout=out, stderr=err,
                timeout=timeout + 20)
            out.seek(0)
            err.seek(0)
            stdout = out.read(65536).decode("utf-8", errors="replace")
            stderr = err.read(65536).decode("utf-8", errors="replace")
        result = subprocess.CompletedProcess(cmd, result.returncode, stdout, stderr)
    except FileNotFoundError as exc:
        raise SandboxUnavailable("Docker CLI is missing") from exc
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
        raise
    if result.returncode == -25:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
        return subprocess.CompletedProcess(cmd, 1, "", "Output exceeded 128 KiB")
    if result.returncode == 125:
        raise SandboxUnavailable(result.stderr[:1000])
    return result


def run_compiler(src, exe, timeout):
    source = Path(src)
    if BACKEND == "docker":
        return _docker(source.parent, ["g++", source.name, "-O2", "-o", Path(exe).name],
                       timeout=timeout, memory="512m")
    if BACKEND != "local":
        raise SandboxUnavailable(f"Unknown backend: {BACKEND}")
    if not shutil.which("g++"):
        raise SandboxUnavailable("g++ is missing")
    return _local(source.parent, ["g++", source.name, "-O2", "-o", Path(exe).name],
                  timeout=timeout, memory=256, output_limit=32 * 1024 * 1024)


def run_program(exe, inp, timeout, seed=None, memory=128):
    program = Path(exe)
    if BACKEND == "local":
        return _local(program.parent, [f"./{program.name}"], input_text=inp,
                      timeout=timeout, memory=memory, seed=seed)
    if BACKEND != "docker":
        raise SandboxUnavailable(f"Unknown backend: {BACKEND}")
    result = _docker(program.parent, ["timeout", f"{timeout}s", f"./{program.name}"],
                     input_text=inp, timeout=timeout, memory=f"{memory}m", seed=seed)
    if result.returncode == 124:
        raise subprocess.TimeoutExpired(program.name, timeout)
    return result
