"""Code Mode (Buổi 7): model viết một đoạn Python, runtime chạy nó, model chỉ nhận stdout.

Code chạy trong tiến trình con (kill được khi quá giờ, Python không dừng được một luồng), chỉ thấy
các hàm được cho phép qua `tools.*`, chỉ import được vài module tính toán, không có `open`. Môi
trường của tiến trình con không chứa secret. Raw dữ liệu ở lại trong runtime; chỉ phần code `print`
(đã cắt) quay về model.
"""

import importlib
import inspect
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel

from agent.tools import Tool

REPO_ROOT = Path(__file__).resolve().parents[2]

# Chạy trong tiến trình con: đọc yêu cầu từ stdin, in đúng một dòng JSON kết quả.
RUNNER = r'''
import builtins, contextlib, importlib, io, json, sys, traceback, types
sys.stdout.reconfigure(encoding="utf-8")  # -I bỏ qua PYTHONIOENCODING
req = json.loads(sys.stdin.read())
sys.path.insert(0, req["root"])
mod = importlib.import_module(req["module"])
tools = types.SimpleNamespace(**{f: getattr(mod, f) for f in req["functions"]})
ALLOWED = {"json", "re", "collections", "itertools", "statistics", "math", "datetime", "fnmatch"}

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".")[0] not in ALLOWED:
        raise ImportError(f"không được import {name}; chỉ cho phép {sorted(ALLOWED)}")
    return builtins.__import__(name, globals, locals, fromlist, level)

# ponytail: chỉ là hàng rào, không phải sandbox: code vẫn thoát được qua __globals__ hay
# __subclasses__. Cần an toàn thật thì chạy trong container không mạng, filesystem chỉ đọc.
safe = {k: v for k, v in vars(builtins).items()
        if k not in {"open", "eval", "exec", "compile", "input", "breakpoint", "__import__"}}
safe["__import__"] = guarded_import

out = io.StringIO()
try:
    with contextlib.redirect_stdout(out):
        exec(compile(req["code"], "<run_code>", "exec"), {"__builtins__": safe, "tools": tools})
    result = {"ok": True, "stdout": out.getvalue()}
except BaseException:
    tail = "\n".join(traceback.format_exc().strip().splitlines()[-4:])
    result = {"ok": False, "stdout": out.getvalue(), "error": tail}
print(json.dumps(result, ensure_ascii=False))
'''


class CodeArgs(BaseModel):
    code: str


def make_run_code_tool(
    module: str,
    functions: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout_s: float = 15.0,
    max_output_chars: int = 4000,
) -> Tool:
    """Tool `run_code`: chạy code của model, code gọi được `tools.<f>` với f thuộc `functions`."""
    mod = importlib.import_module(module)
    fns = [getattr(mod, f) for f in functions]
    api = "\n".join(
        f"- tools.{fn.__name__}{inspect.signature(fn)}: "
        f"{(inspect.getdoc(fn) or '').partition(chr(10))[0]}"
        for fn in fns
    )
    # Windows cần SYSTEMROOT để Python khởi động; ngoài ra chỉ truyền đúng `env`, không lộ .env.
    child_env = {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ} | dict(env or {})
    request = {"root": str(REPO_ROOT), "module": module, "functions": list(functions)}

    def run_code(args: CodeArgs) -> dict:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", RUNNER],
                input=json.dumps({**request, "code": args.code}),
                capture_output=True, text=True, encoding="utf-8",
                timeout=timeout_s, env=child_env,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"code chạy quá {timeout_s}s, đã bị dừng") from None
        lines = proc.stdout.strip().splitlines()
        if not lines:
            raise RuntimeError(f"runtime lỗi: {proc.stderr.strip()[-500:]}")
        result = json.loads(lines[-1])
        if not result["ok"]:
            raise RuntimeError(result["error"])
        stdout = result["stdout"]
        return {"stdout": stdout[:max_output_chars], "truncated": len(stdout) > max_output_chars}

    description = (
        "Chạy một chương trình Python. Trong code có sẵn đối tượng `tools` với các hàm:\n"
        f"{api}\n"
        "Chỉ import được json, re, collections, itertools, statistics, math, datetime, fnmatch; "
        "không có open(). Dùng vòng lặp để đọc và tổng hợp nhiều nguồn trong code. Chỉ print kết "
        f"quả cuối đã tổng hợp, không in dữ liệu thô (stdout bị cắt ở {max_output_chars} ký tự)."
    )
    return Tool("run_code", description, CodeArgs, run_code,
                timeout_s=timeout_s + 5, max_retries=0)
