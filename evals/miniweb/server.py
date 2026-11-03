"""Server mini-web phục vụ kho trang snapshot cho eval và kiểm thử (Phase 2, Task 3).

Chỉ import từ evals/ và fastapi, uvicorn, pyyaml (docker compose chỉ mount thư mục evals/):
không import từ agent/ hay data/.
"""

import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

BASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = BASE_DIR / "manifest.yaml"

app = FastAPI(title="Mini-web Server", description="Server snapshot cho eval UC-02")


def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"domains": {}, "pages": []}
    content = MANIFEST_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        return {"domains": {}, "pages": []}
    return data


def _normalize_host_path_query(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().rstrip(".")
    if ":" in host:
        host = host.split(":")[0]
    path = parsed.path.strip("/")
    query = parsed.query.strip()
    return host, path, query


def _extract_title_text(html: str) -> tuple[str, str]:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_m.group(1).strip() if title_m else ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


@app.get("/search")
async def search(
    q: str = Query(default="", description="Từ khoá tìm kiếm"),
    n: int = Query(default=5, ge=1, le=10, description="Số kết quả tối đa"),
) -> dict:
    manifest = load_manifest()
    pages = manifest.get("pages", [])
    query = q.strip().lower()
    if not query:
        return {"results": []}

    results = []
    pages_root = (BASE_DIR / "pages").resolve()

    for page in pages:
        file_rel = page.get("file")
        if not file_rel:
            continue
        file_path = (BASE_DIR / file_rel).resolve()

        # Bảo vệ: không tìm kiếm hoặc đọc file ngoài thư mục pages/
        try:
            file_path.relative_to(pages_root)
        except ValueError:
            continue

        if "answer_key" in str(file_path).lower() or not file_path.is_file():
            continue

        try:
            html = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        title, text = _extract_title_text(html)
        if query in title.lower() or query in text.lower():
            pos = text.lower().find(query)
            if pos >= 0:
                start = max(0, pos - 50)
                end = min(len(text), pos + len(query) + 100)
                snippet = text[start:end].strip()
            else:
                snippet = text[:150].strip()

            results.append({
                "url": page.get("url", ""),
                "title": title,
                "snippet": snippet,
            })
            if len(results) >= n:
                break

    return {"results": results}


@app.get("/{host}/{path:path}")
async def serve_page(host: str, path: str, request: Request):
    # Chặn path traversal và file answer_key (không phân biệt hoa thường)
    raw_path = request.url.path.lower()
    if "answer_key" in raw_path or ".." in raw_path:
        raise HTTPException(status_code=404, detail="Không tìm thấy trang")

    manifest = load_manifest()
    pages = manifest.get("pages", [])

    req_host = host.lower().rstrip(".")
    if ":" in req_host:
        req_host = req_host.split(":")[0]
    req_path = path.strip("/")
    req_query = request.url.query.strip()

    # Tìm trang khớp cả host, path và query nếu query được định nghĩa
    matched_page = None
    fallback_match = None

    for page in pages:
        p_host, p_path, p_query = _normalize_host_path_query(page.get("url", ""))
        if p_host == req_host and p_path == req_path:
            if p_query and req_query and p_query == req_query:
                matched_page = page
                break
            if not p_query and not req_query:
                matched_page = page
                break
            if fallback_match is None:
                fallback_match = page

    if not matched_page:
        matched_page = fallback_match

    if not matched_page:
        raise HTTPException(status_code=404, detail="Trang không có trong manifest")

    delay_s = matched_page.get("delay_s")
    if delay_s and delay_s > 0:
        await asyncio.sleep(delay_s)

    redirect_to = matched_page.get("redirect_to")
    if redirect_to:
        return RedirectResponse(url=redirect_to, status_code=302)

    file_rel = matched_page.get("file")
    if file_rel:
        file_path = (BASE_DIR / file_rel).resolve()
        pages_root = (BASE_DIR / "pages").resolve()
        # Chắc chắn file nằm trong thư mục pages/
        try:
            file_path.relative_to(pages_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="File ngoài thư mục pages") from None

        if not file_path.is_file() or "answer_key" in str(file_path).lower():
            raise HTTPException(status_code=404, detail="File trang không tồn tại")

        content = file_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content, media_type="text/html")

    raise HTTPException(status_code=404, detail="Cấu hình trang không hợp lệ")
