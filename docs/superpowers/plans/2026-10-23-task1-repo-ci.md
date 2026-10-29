# Task 1 (Repo + CI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng khung repo Python cài được bằng `pip install -e ".[dev]"`, có `.env.example`, `.gitignore` đúng, và CI GitHub Actions chạy `ruff`, `pytest`, quét secret trên mọi push/PR.

**Architecture:** Một `pyproject.toml` (setuptools, flat layout, chỉ đóng gói `agent` và `evals`). Thư mục rỗng giữ bằng `__init__.py` (package Python) hoặc `.gitkeep`. `tests/test_smoke.py` kiểm bằng code: package import được, `.env.example` đủ biến và để trống, `.gitignore` bỏ/giữ đúng đường dẫn. CI có 2 job: `lint-test` và `secrets` (gitleaks).

**Tech Stack:** Python ≥ 3.11 (CI dùng 3.12), setuptools, pytest, ruff, GitHub Actions, gitleaks-action v2.

**Spec:** [docs/roadmap/phase-1.md](../../roadmap/phase-1.md) mục "Task 1: Repo + CI" (issue #2). Đọc kèm [AGENTS.md](../../../AGENTS.md) luật cứng 8 (secret chỉ nằm trong `.env`).

## Global Constraints

- Dependencies đúng DoD: `google-genai`, `pydantic`, `fastapi`; dev: `pytest`, `ruff`. Không thêm thư viện khác ở task này (PyYAML, python-dotenv, uvicorn do task cần chúng tự thêm).
- `.env.example` có `GEMINI_API_KEY=`, `GEMINI_MODEL=`, `GEMINI_EMBED_MODEL=`, **mọi giá trị để trống**. Không ghi tên model cứng ở đâu cả (D-02).
- `.gitignore` bỏ qua `traces/*` nhưng giữ `traces/samples/`.
- Mọi lần mở file văn bản trong code/test dùng `encoding="utf-8"` (máy Windows mặc định cp1252).
- Không có Docker Compose, Postgres, WordPress ở task này (để Phase 2).
- Nhánh: `feature/issue-2-repo-ci`, tách từ `origin/develop`; PR vào `develop` (nhánh mặc định, repo không có `main`).
- Commit theo kiểu đã dùng (`feat:`, `ci:`, `doc:`); commit có AI hỗ trợ giữ trailer `Co-Authored-By` (AGENTS.md, mục Quy ước).

## Review Focus

1. Thành viên chạy `pip install -e` rồi `git add -A`: `*.egg-info/`, `.venv/`, `__pycache__/` không được lọt vào commit (cache của pytest và ruff tự có `.gitignore` riêng). Kiểm ở `test_gitignore_ignores` (Task B).
2. Ai đó điền key thật vào `.env.example` thay vì `.env`: test phải đỏ trước cả gitleaks. Kiểm ở `test_env_example_has_no_values` (Task B).
3. Trace của run thật (`traces/<run_id>.jsonl`) bị commit, trong khi trace mẫu ở `traces/samples/` (Task 6 cần) phải commit được. Kiểm ở `test_gitignore_ignores` / `test_gitignore_keeps` (Task B).
4. `.env.example` có comment tiếng Việt, đọc trên Windows không chỉ định encoding sẽ `UnicodeDecodeError`. Kiểm bằng cách chạy `pytest` trên máy Windows ở Task B Step 4 (helper đọc bằng `utf-8`).
5. Setuptools báo "Multiple top-level packages discovered in a flat-layout" khi repo có `app/`, `tests/`, `skills/`, `data/`. Chặn bằng `[tool.setuptools.packages.find] include`; kiểm bằng bước `pip install -e` ở Task A và trong CI (Task C).

---

### Task A: Khung package + `pyproject.toml`

**Files:**
- Create: `pyproject.toml`
- Create: `agent/__init__.py`, `evals/__init__.py` (rỗng)
- Create: `app/backend/.gitkeep`, `app/frontend/.gitkeep`, `skills/.gitkeep`, `data/brand/.gitkeep`, `traces/samples/.gitkeep` (rỗng)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: không.
- Produces: package `agent` và `evals` import được sau `pip install -e ".[dev]"`; lệnh `ruff check .` và `pytest` (chỉ quét `tests/`) chạy từ gốc repo. Task 3 trở đi thêm module vào `agent/`, Task 8 thêm `evals/run.py` để chạy `python -m evals.run`.

- [ ] **Step 1: Tạo nhánh và môi trường ảo**

```bash
git fetch origin
git switch -c feature/issue-2-repo-ci origin/develop
uv venv --seed --python 3.12 .venv      # hoặc: python -m venv .venv
source .venv/Scripts/activate           # PowerShell: .venv\Scripts\Activate.ps1
```

Expected: `python --version` in ra `Python 3.12.x`.

- [ ] **Step 2: Viết test thất bại**

`tests/test_smoke.py`:

```python
import importlib

import pytest


@pytest.mark.parametrize("name", ["agent", "evals"])
def test_package_imports(name):
    importlib.import_module(name)
```

- [ ] **Step 3: Chạy test, xác nhận thất bại**

Run: `python -m pip install pytest && python -m pytest tests/test_smoke.py -v`
Expected: 2 FAIL với `ModuleNotFoundError: No module named 'agent'` / `'evals'`.

- [ ] **Step 4: Tạo `pyproject.toml`, hai package và các thư mục giữ chỗ**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "geo-content-writer-agent"
version = "0.1.0"
description = "Agent viết blog tiếng Việt tối ưu GEO cho thương hiệu hư cấu Skyveil (SE373)"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "google-genai>=1.0",
    "pydantic>=2.7",
    "fastapi>=0.115",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.setuptools.packages.find]
include = ["agent*", "evals*"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`agent/__init__.py`, `evals/__init__.py` và 5 file `.gitkeep` đều rỗng. `app/` **không** có `__init__.py` (Task 7 tự quyết cách chạy backend).

- [ ] **Step 5: Cài và chạy lại**

Run: `python -m pip install -e ".[dev]" && ruff check . && pytest -v`
Expected: pip kết thúc bằng `Successfully installed ... geo-content-writer-agent-0.1.0`, không có dòng "Multiple top-level packages"; `All checks passed!`; `2 passed`.

- [ ] **Step 6: Commit** (add từng đường dẫn; `.gitignore` chưa chặn `*.egg-info/`, nên **không** dùng `git add -A`)

```bash
git add pyproject.toml agent/__init__.py evals/__init__.py tests/test_smoke.py \
  app/backend/.gitkeep app/frontend/.gitkeep skills/.gitkeep data/brand/.gitkeep traces/samples/.gitkeep
git commit -m "feat: add pyproject and package skeleton"
```

---

### Task B: `.env.example` + `.gitignore`

**Files:**
- Create: `.env.example`
- Modify: `.gitignore` (hiện có 5 dòng: `.env`, `.env.*`, `!.env.example`, `__pycache__/`, `.venv/`)
- Test: `tests/test_smoke.py` (thêm vào)

**Interfaces:**
- Consumes: `tests/test_smoke.py` và `pytest` từ Task A.
- Produces: tên biến môi trường `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBED_MODEL` (Task 3 đọc hai biến đầu, Task 4 đọc `GEMINI_EMBED_MODEL`). Thư mục `traces/` được ignore trừ `traces/samples/` (Task 6 ghi trace vào `traces/<run_id>.jsonl`).

- [ ] **Step 1: Viết test thất bại** (thêm vào `tests/test_smoke.py`; gộp import lên đầu file để ruff `I` không báo)

```python
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEMINI_VARS = {"GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_EMBED_MODEL"}


def _env_example() -> dict[str, str]:
    pairs = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            pairs[key.strip()] = value.strip()
    return pairs


def test_env_example_lists_gemini_vars():
    assert GEMINI_VARS <= _env_example().keys()


def test_env_example_has_no_values():
    assert {k: v for k, v in _env_example().items() if v} == {}


def _ignored(path: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT)
    assert r.returncode in (0, 1), f"git check-ignore lỗi với {path}"
    return r.returncode == 0


@pytest.mark.parametrize("path", [
    ".env",
    ".env.local",
    "traces/0a1b2c.jsonl",
    ".venv/pyvenv.cfg",
    "geo_content_writer_agent.egg-info/PKG-INFO",
    "agent/__pycache__/x.pyc",
])
def test_gitignore_ignores(path):
    assert _ignored(path)


@pytest.mark.parametrize("path", [
    ".env.example",
    "traces/samples/0a1b2c.jsonl",
    "traces/samples/.gitkeep",
])
def test_gitignore_keeps(path):
    assert not _ignored(path)
```

`--no-index` để kiểm theo mẫu trong `.gitignore`, không phụ thuộc file đã track hay chưa; đường dẫn không cần tồn tại.

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `pytest -v`
Expected: 2 test `.env.example` FAIL với `FileNotFoundError`; `test_gitignore_ignores` FAIL ở `traces/0a1b2c.jsonl` và `geo_content_writer_agent.egg-info/PKG-INFO`; các test còn lại PASS.

- [ ] **Step 3: Tạo `.env.example` và sửa `.gitignore`**

`.env.example` (comment tiếng Việt là cố ý, để Review Focus 4 được kiểm):

```dotenv
# Sao chép file này thành .env rồi điền giá trị. Không commit .env.
# Lấy key tại https://aistudio.google.com/apikey
GEMINI_API_KEY=
# Model sinh văn bản (D-02). Chọn khi làm Task 3.
GEMINI_MODEL=
# Model embedding, dùng cho tool dedupe_prompts (Task 4).
GEMINI_EMBED_MODEL=
```

`.gitignore`: giữ 5 dòng cũ, thêm vào cuối:

```gitignore
*.egg-info/
traces/*
!traces/samples/
```

Phải là `traces/*`, không phải `traces/`: ignore cả thư mục thì git không xét dòng `!` bên trong nữa.

- [ ] **Step 4: Chạy lại trên máy Windows**

Run: `ruff check . && pytest -v`
Expected: `All checks passed!`; `13 passed` (2 import + 2 env + 6 ignore + 3 keep). Chạy trên Windows để chứng minh helper đọc tiếng Việt bằng `utf-8`.

- [ ] **Step 5: Kiểm `git status` sạch rác**

Run: `git status --short`
Expected: chỉ có `.env.example`, `.gitignore`, `tests/test_smoke.py`; không có `.venv/`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`.

- [ ] **Step 6: Commit**

```bash
git add .env.example .gitignore tests/test_smoke.py
git commit -m "feat: add .env.example and ignore traces and build dirs"
```

---

### Task C: CI + PR + cập nhật roadmap

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `docs/roadmap/phase-1.md` (dòng Task 1 trong Bảng tiến độ, các ô DoD của Task 1)
- Modify: `AGENTS.md` (mục "Cấu trúc repo dự kiến", mục "Quy ước")

**Interfaces:**
- Consumes: lệnh `pip install -e ".[dev]"`, `ruff check .`, `pytest` từ Task A, B.
- Produces: workflow `CI` với job `lint-test` và `secrets`. Task 7 thêm job build frontend (`npm ci && npm run build`) vào file này; Task 8 có thể thêm bước eval.

- [ ] **Step 1: Viết `.github/workflows/ci.yml`**

```yaml
name: CI

on: [push, pull_request]

permissions:
  contents: read

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -v

  secrets:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`fetch-depth: 0` bắt buộc: gitleaks cần toàn bộ lịch sử để quét các commit của PR. gitleaks-action miễn phí cho repo cá nhân; nếu repo chuyển sang organization (ví dụ GitHub Classroom) thì cần thêm secret `GITLEAKS_LICENSE` (đăng ký miễn phí tại gitleaks.io).

- [ ] **Step 2: Commit, push, mở PR**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run ruff, pytest and gitleaks on every push and PR"
git push -u origin feature/issue-2-repo-ci
gh pr create --base develop --title "[Phase 1][Task 1] Repo + CI" --body "Closes #2"
```

Expected: `gh` in ra URL PR mới.

- [ ] **Step 3: Chờ CI và xác nhận xanh**

Run: `gh pr checks --watch`
Expected: `lint-test` và `secrets` đều `pass` (cả lượt `push` lẫn `pull_request`). Nếu đỏ: `gh run view --log-failed`, sửa, push lại.

- [ ] **Step 4: Cập nhật roadmap và AGENTS.md** (theo mục "Cách cập nhật" của phase-1.md)

- `docs/roadmap/phase-1.md`: tick 5 ô DoD của Task 1; dòng Task 1 trong Bảng tiến độ thành Owner `@NguyenHungCuongg`, trạng thái `✅`, cột PR là link PR vừa tạo.
- `AGENTS.md`, khối "Cấu trúc repo dự kiến": thêm dòng `agent/` (code agent), `app/backend/`, `app/frontend/`, `tests/` (pytest), `traces/` (trace từng run, chỉ commit `traces/samples/`), `.github/workflows/ci.yml`.
- `AGENTS.md`, mục "Quy ước": thêm một dòng "Trước khi push: `ruff check .` và `pytest` phải xanh; CI chạy lại cả hai và quét secret bằng gitleaks."

- [ ] **Step 5: Commit, push, xác nhận CI vẫn xanh**

```bash
git add docs/roadmap/phase-1.md AGENTS.md
git commit -m "doc: mark Task 1 done in phase-1 roadmap"
git push
gh pr checks --watch
```

Expected: cả hai job `pass`. PR sẵn sàng review; merge vào `develop` sẽ tự đóng issue #2.
