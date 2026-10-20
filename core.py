import asyncio
import json
import os
import subprocess
import tempfile

DATA_FILE = "data.json"
NUM_TESTS = 10
TIMEOUT = 2
COMPILE_TIMEOUT = 30  # giây, cho mỗi lần gọi g++

_problems = {}
_user_inputs = {}


def load_data():
    global _problems, _user_inputs
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _problems = data.get("de", {})
                _user_inputs = data.get("inp_data", {})
        except (json.JSONDecodeError, ValueError, IOError):
            _problems, _user_inputs = {}, {}
    else:
        _problems, _user_inputs = {}, {}


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"inp_data": _user_inputs, "de": _problems},
                  f, ensure_ascii=False, indent=4)


load_data()


def strip_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```") and code.endswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1]) if len(lines) >= 2 else code.strip("`")
    return code.replace("```cpp\n", "").replace("```", "")


def create_problem(name: str) -> bool:
    if name in _problems:
        return False
    _problems[name] = {"question": "", "solution": "", "gen_test": "",
                       "checker": "", "category": "Chưa phân loại"}
    save_data()
    return True


def set_problem_field(name: str, field: str, code: str) -> bool:
    if name not in _problems:
        return False
    _problems[name][field] = code
    save_data()
    return True


def get_problem(name: str):
    return _problems.get(name)


def list_problems() -> dict:
    cats = {}
    for name, data in _problems.items():
        cats.setdefault(data.get("category", "Chưa phân loại"), []).append(name)
    return cats


def set_category(name: str, cat: str) -> bool:
    if name not in _problems:
        return False
    _problems[name]["category"] = cat
    save_data()
    return True


def set_user_input(user_id: str, inp: str):
    _user_inputs[user_id] = inp
    save_data()


def get_user_input(user_id: str) -> str:
    return _user_inputs.get(user_id, "")


async def is_ac(inp: str, sol: str, out: str, checker_exe: str) -> bool:
    if not checker_exe:
        return sol.strip() == out.strip()
    check = inp + "\nENDINP\n" + sol + "\nENDOUT\n" + out
    try:
        proc = await asyncio.to_thread(
            subprocess.run, [checker_exe], input=check,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "AC"
    except subprocess.TimeoutExpired:
        return False


async def _compile(src: str, exe: str):
    """Biên dịch bằng g++. Trả về CompletedProcess, hoặc None nếu máy chưa cài g++.
    Hết thời gian thì giả lập lỗi biên dịch để caller báo CE như thường."""
    try:
        return await asyncio.to_thread(
            subprocess.run, ["g++", src, "-O2", "-o", exe],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["g++"], returncode=1, stdout="",
            stderr=f"Biên dịch quá thời gian cho phép ({COMPILE_TIMEOUT}s).",
        )


async def _run(exe: str, inp: str):
    return await asyncio.to_thread(
        subprocess.run, [exe], input=inp,
        capture_output=True, text=True, timeout=TIMEOUT,
    )


async def judge(name: str, code: str):
    p = get_problem(name)
    if p is None:
        yield {"t": "not_found"}
        return

    yield {"t": "status", "msg": "compiling"}

    with tempfile.TemporaryDirectory() as d:
        cpp, sol_f, gen_f = (os.path.join(d, n) for n in ("temp.cpp", "solution.cpp", "gen_test.cpp"))
        exe, exe_sol, exe_gen = (os.path.join(d, n) for n in ("temp", "solution", "gen_test"))
        for path, content in ((cpp, code), (sol_f, p["solution"]), (gen_f, p["gen_test"])):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        checker_exe = ""
        if p["checker"]:
            chk_f = os.path.join(d, "checker.cpp")
            checker_exe = os.path.join(d, "checker")
            with open(chk_f, "w", encoding="utf-8") as f:
                f.write(p["checker"])
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
        r = await _compile(gen_f, exe_gen)
        if r is None:
            yield {"t": "sys", "msg": "no_compiler"}
            return
        if r.returncode != 0:
            yield {"t": "ce", "who": "gen", "stderr": r.stderr}
            return

        yield {"t": "status", "msg": "testing"}

        for i in range(1, NUM_TESTS + 1):
            try:
                g = await _run(exe_gen, "")
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
                s = await _run(exe_sol, inp)
            except subprocess.TimeoutExpired:
                yield {"t": "sys", "msg": "sol_tle"}
                return
            if s.returncode != 0:
                yield {"t": "sys", "msg": "sol_rte", "detail": s.stderr}
                return

            try:
                u = await _run(exe, inp)
            except subprocess.TimeoutExpired:
                yield {"t": "tle", "test": i}
                return
            if u.returncode != 0 or u.stderr != "":
                yield {"t": "rte", "test": i, "stderr": u.stderr}
                return
            if not await is_ac(inp, s.stdout, u.stdout, checker_exe):
                yield {"t": "wa", "test": i,
                       "inp": inp, "sol": s.stdout, "out": u.stdout}
                return

        yield {"t": "ac"}


async def run_once(code: str, inp: str):
    with tempfile.TemporaryDirectory() as d:
        cpp = os.path.join(d, "temp.cpp")
        exe = os.path.join(d, "temp")
        with open(cpp, "w", encoding="utf-8") as f:
            f.write(code)
        r = await _compile(cpp, exe)
        if r is None:
            return {"t": "ce", "stderr": "Máy chấm chưa cài g++, không biên dịch được. Báo admin cài giúp nhé!"}
        if r.returncode != 0:
            return {"t": "ce", "stderr": r.stderr}
        try:
            u = await _run(exe, inp)
        except subprocess.TimeoutExpired:
            return {"t": "tle"}
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
    cout << k * 2 << '\\n';
}"""

SAMPLE_GEN = """#include<bits/stdc++.h>
using namespace std;

mt19937_64 rng(chrono::steady_clock::now().time_since_epoch().count());

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
