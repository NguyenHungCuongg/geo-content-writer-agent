"""Server mini-web phục vụ kho trang snapshot cho eval và kiểm thử (Phase 2, Task 3).

Chỉ import từ evals/ và fastapi, uvicorn, pyyaml (docker compose chỉ mount thư mục evals/):
không import từ agent/ hay data/.
"""

import asyncio
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

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


def _clean_host(host: str) -> str:
    h = host.lower().rstrip(".")
    return h.split(":")[0] if ":" in h else h


def _normalize_host_path_query(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    host = _clean_host(parsed.netloc)
    path = unquote(parsed.path).strip("/")
    query = unquote(parsed.query).strip()
    return host, path, query


def _safe_resolve_page(file_rel: str | None) -> Path | None:
    if not file_rel:
        return None
    file_path = (BASE_DIR / file_rel).resolve()
    pages_root = (BASE_DIR / "pages").resolve()
    try:
        file_path.relative_to(pages_root)
    except ValueError:
        return None
    if "answer_key" in str(file_path).lower() or not file_path.is_file():
        return None
    return file_path


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

    query_words = list(dict.fromkeys(w for w in query.split() if w))
    if not query_words:
        return {"results": []}

    scored = []

    for idx, page in enumerate(pages):
        file_path = _safe_resolve_page(page.get("file"))
        if file_path is None:
            continue

        try:
            html = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        title, text = _extract_title_text(html)
        full_content = (title + " " + text).lower()

        matched_words = sum(1 for w in query_words if w in full_content)
        if matched_words == 0:
            continue

        exact_phrase = query in full_content

        # Tạo snippet: ưu tiên cụm truy vấn đầy đủ, nếu không lấy từ đầu tiên khớp
        if exact_phrase:
            pos = text.lower().find(query)
            if pos >= 0:
                start = max(0, pos - 50)
                end = min(len(text), pos + len(query) + 100)
                snippet = text[start:end].strip()
            else:
                snippet = text[:150].strip()
        else:
            first_pos = -1
            for w in query_words:
                pos = text.lower().find(w)
                if pos >= 0:
                    if first_pos == -1 or pos < first_pos:
                        first_pos = pos
            if first_pos >= 0:
                start = max(0, first_pos - 50)
                end = min(len(text), first_pos + 150)
                snippet = text[start:end].strip()
            else:
                snippet = text[:150].strip()

        scored.append({
            "matched_words": matched_words,
            "exact_phrase": exact_phrase,
            "manifest_index": idx,
            "result": {
                "url": page.get("url", ""),
                "title": title,
                "snippet": snippet,
            },
        })

    # Xếp theo số từ trùng giảm dần, khớp cả cụm từ, giữ thứ tự manifest nếu bằng nhau
    scored.sort(
        key=lambda x: (x["matched_words"], x["exact_phrase"], -x["manifest_index"]),
        reverse=True,
    )
    return {"results": [item["result"] for item in scored[:n]]}


@app.get("/{host}/{path:path}")
async def serve_page(host: str, path: str, request: Request):
    # Chặn path traversal và file answer_key (không phân biệt hoa thường)
    raw_path = unquote(request.url.path).lower()
    if "answer_key" in raw_path or ".." in raw_path:
        raise HTTPException(status_code=404, detail="Không tìm thấy trang")

    manifest = load_manifest()
    pages = manifest.get("pages", [])

    req_host = _clean_host(host)
    req_path = unquote(path).strip("/")
    req_query = unquote(request.url.query).strip()

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
        file_path = _safe_resolve_page(file_rel)
        if file_path is None:
            raise HTTPException(
                status_code=404, detail="File trang không tồn tại hoặc không hợp lệ"
            )

        content = file_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content, media_type="text/html")

    raise HTTPException(status_code=404, detail="Cấu hình trang không hợp lệ")
