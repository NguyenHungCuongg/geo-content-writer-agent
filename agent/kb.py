"""Kho tri thức (Knowledge Base) và RAG có trích dẫn (Phase 2, Task 4 - UC-02b).

Bao gồm:
- Data models: Chunk, Hit, Citation, IngestResult
- Protocol KB, bản MemoryKB (trong RAM) và PgKB (Postgres + pgvector)
- Phân đoạn trang (chunk_page), so khớp chuỗi trích dẫn (quote_in, check_citation)
- Nạp mini-web (ingest_miniweb), nạp brand kit (ingest_brand_kit)
- Kiểm tra toàn bộ URL trong kho thuộc allowlist (check_kb_allowlist)
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
import trafilatura
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

from agent.llm import require_env
from agent.tools.web import Page, find_suspicious, tier_of

BRAND_KIT_PATH = Path(__file__).resolve().parents[1] / "data" / "brand" / "brand_kit.yaml"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "evals" / "miniweb" / "manifest.yaml"


class Chunk(BaseModel):
    id: str  # <sha1(url)[:12]>:<số thứ tự>
    url: str
    domain: str
    title: str
    published_at: str | None = None
    fetched_at: str
    trust_tier: Literal["A", "B", "C", "brand"]
    text: str
    suspicious: bool = False
    content_hash: str = ""


class Hit(Chunk):
    score: float


class Citation(BaseModel):
    n: int
    chunk_id: str
    url: str
    quote: str


class IngestResult(BaseModel):
    url: str
    chunks: int
    suspicious: int
    duplicate: bool


class KB(Protocol):
    def ingest(self, page: Page, *, tracer: Any = None) -> IngestResult:
        ...

    def search(self, query: str, k: int = 5) -> list[Hit]:
        ...

    def get(self, chunk_id: str) -> Chunk | None:
        ...


def remove_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để phục vụ full-text search simple của Postgres."""
    nfd = unicodedata.normalize("NFD", text)
    no_combining = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return no_combining.replace("đ", "d").replace("Đ", "D")


def quote_in(quote: str, text: str) -> bool:
    """So chuỗi con sau khi chuẩn hoá NFC và gộp khoảng trắng.

    Trang nguồn có thể lưu tiếng Việt dạng tổ hợp (NFD), model trả dạng dựng sẵn (NFC);
    chuẩn hoá NFC và khoảng trắng cả hai phía rồi mới so (Lỗi dễ bị bỏ sót số 2).
    """
    if not quote or not text:
        return False
    norm_quote = re.sub(r"\s+", " ", unicodedata.normalize("NFC", quote)).strip()
    norm_text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()
    return norm_quote in norm_text


def check_citation(c: Citation, kb: KB) -> str | None:
    """Kiểm tra trích dẫn: chunk tồn tại, URL khớp, không suspicious, và đoạn trích nằm trong chunk.

    Trả None nếu hợp lệ, ngược lại trả chuỗi mô tả lỗi.
    """
    chunk = kb.get(c.chunk_id)
    if chunk is None:
        return f"Chunk {c.chunk_id} không tồn tại trong kho tri thức"
    if chunk.suspicious:
        return f"Chunk {c.chunk_id} bị gắn cờ nghi vấn (suspicious), không được dùng làm trích dẫn"
    if chunk.url != c.url:
        return f"URL của trích dẫn ({c.url}) không khớp URL của chunk ({chunk.url})"
    if not quote_in(c.quote, chunk.text):
        return f"Đoạn trích '{c.quote}' không nằm trong nội dung chunk {c.chunk_id}"
    return None


def _split_into_blocks(text: str) -> list[str]:
    """Tách văn bản thành các khối đoạn/tiêu đề tự nhiên."""
    if not text.strip():
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paras) <= 1 and "\n" in text:
        paras = [p.strip() for p in text.splitlines() if p.strip()]
    return paras


def _slide_window(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """Cắt văn bản dài thành các đoạn gối overlap."""
    if len(text) <= max_chars:
        return [text]
    step = max(1, max_chars - overlap)
    slices: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        slices.append(text[start:end])
        if end == len(text):
            break
        start += step
    return slices


def chunk_page(page: Page) -> list[Chunk]:
    """Cắt theo heading và đoạn trước, chunk còn dài hơn 1.200 ký tự thì cắt tiếp, gối 200 ký tự.

    Chunk chứa câu find_suspicious bắt được thì suspicious=True.
    Chunk id có định dạng: <sha1(url)[:12]>:<số thứ tự>
    """
    if not page.text or not page.text.strip():
        return []

    url_hash = hashlib.sha1(page.url.encode("utf-8")).hexdigest()[:12]

    if page.url.startswith("brand-kit://"):
        domain = "brand-kit"
        tier: Literal["A", "B", "C", "brand"] = "brand"
    else:
        try:
            parsed = httpx.URL(page.url)
            domain = parsed.host.lower().rstrip(".") if parsed.host else ""
        except Exception:
            domain = ""
        tier = tier_of(page.url) or "C"

    page_suspicious_sentences = find_suspicious(page.text)
    chash = hashlib.sha256(page.text.strip().encode("utf-8")).hexdigest()
    blocks = _split_into_blocks(page.text)
    raw_chunks: list[str] = []
    current_acc: list[str] = []
    current_len = 0

    def is_heading(line: str) -> bool:
        s = line.strip()
        if s.startswith(("#", "==")):
            return True
        if len(s) < 80 and not s.endswith((".", "!", "?", ";", ",")):
            return True
        return False

    for b in blocks:
        if is_heading(b) and current_acc:
            raw_chunks.append("\n\n".join(current_acc))
            current_acc = []
            current_len = 0

        # Nếu block dài hơn 1200 ký tự, xả current_acc rồi cắt block thành các đoạn gối
        if len(b) > 1200:
            if current_acc:
                raw_chunks.append("\n\n".join(current_acc))
                current_acc = []
                current_len = 0
            raw_chunks.extend(_slide_window(b, max_chars=1200, overlap=200))
            continue

        if current_len + len(b) + 2 <= 1200:
            current_acc.append(b)
            current_len += len(b) + 2
        else:
            if current_acc:
                raw_chunks.append("\n\n".join(current_acc))
            current_acc = [b]
            current_len = len(b)

    if current_acc:
        raw_chunks.append("\n\n".join(current_acc))

    final_texts: list[str] = []
    for rc in raw_chunks:
        final_texts.extend(_slide_window(rc, max_chars=1200, overlap=200))

    chunks: list[Chunk] = []
    for idx, ctext in enumerate(final_texts):
        suspicious = (
            len(find_suspicious(ctext)) > 0
            or any(s in ctext for s in page_suspicious_sentences)
        )
        chunks.append(
            Chunk(
                id=f"{url_hash}:{idx}",
                url=page.url,
                domain=domain,
                title=page.title,
                published_at=page.published_at,
                fetched_at=page.fetched_at,
                trust_tier=tier,
                text=ctext,
                suspicious=suspicious,
                content_hash=chash,
            )
        )
    return chunks


class MemoryKB:
    """Kho tri thức trong RAM: xếp hạng theo số từ trùng. Dùng cho test và eval offline."""

    def __init__(self, chunks: Sequence[Chunk] = ()):
        self._chunks: dict[str, Chunk] = {c.id: c for c in chunks}
        # Lưu content_hash -> url để phát hiện trang trùng nội dung
        self._content_hashes: dict[str, str] = {}
        for c in chunks:
            h = c.content_hash or hashlib.sha256(c.text.strip().encode("utf-8")).hexdigest()
            self._content_hashes.setdefault(h, c.url)

    def ingest(self, page: Page, *, tracer: Any = None) -> IngestResult:
        chash = hashlib.sha256(page.text.strip().encode("utf-8")).hexdigest()
        if chash in self._content_hashes:
            # Trang trùng nội dung: không lưu thêm chunk
            existing = [c for c in self._chunks.values() if c.url == self._content_hashes[chash]]
            susp = sum(1 for c in existing if c.suspicious)
            if susp > 0 and tracer is not None:
                tracer.log(
                    "decision", action="flag_suspicious", url=page.url, count=susp
                )
            return IngestResult(url=page.url, chunks=0, suspicious=susp, duplicate=True)

        self._content_hashes[chash] = page.url
        page_chunks = chunk_page(page)
        suspicious_count = 0
        for c in page_chunks:
            self._chunks[c.id] = c
            if c.suspicious:
                suspicious_count += 1

        if suspicious_count > 0 and tracer is not None:
            tracer.log("decision", action="flag_suspicious", url=page.url, count=suspicious_count)

        return IngestResult(
            url=page.url,
            chunks=len(page_chunks),
            suspicious=suspicious_count,
            duplicate=False,
        )

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        # Không bao giờ trả chunk suspicious
        candidates = [c for c in self._chunks.values() if not c.suspicious]
        query_words = set(re.findall(r"\w+", remove_accents(query.lower())))
        scored: list[tuple[float, Chunk]] = []

        for c in candidates:
            c_words = re.findall(r"\w+", remove_accents(c.text.lower()))
            score = sum(1 for w in c_words if w in query_words)
            if score > 0:
                scored.append((float(score), c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            Hit(**c.model_dump(), score=s)
            for s, c in scored[:k]
        ]


def _row_to_chunk(r: tuple[Any, ...]) -> Chunk:
    """Chuyển một hàng từ bảng chunks thành đối tượng Chunk."""
    if len(r) == 9 and isinstance(r[8], bool):
        return Chunk(
            id=r[0],
            url=r[1],
            domain=r[2],
            title=r[3],
            published_at=r[4],
            fetched_at=r[5],
            trust_tier=r[6],
            text=r[7],
            suspicious=r[8],
            content_hash="",
        )
    return Chunk(
        id=r[0],
        url=r[1],
        domain=r[2],
        title=r[3],
        published_at=r[4],
        fetched_at=r[5],
        trust_tier=r[6],
        text=r[7],
        content_hash=str(r[8]) if len(r) > 8 and r[8] is not None else "",
        suspicious=bool(r[9]) if len(r) > 9 and r[9] is not None else False,
    )


class PgKB:
    """Kho tri thức trên Postgres + pgvector với tìm kiếm hybrid (cosine + FTS, RRF k=60)."""

    def __init__(
        self,
        conn: Any,
        *,
        mode: Literal["hybrid", "vector"] = "hybrid",
        embed: Callable[[list[str]], list[list[float]]] | None = None,
    ):
        self.conn = conn
        self.mode = mode
        self.embed = embed

    def _default_gemini_embed(self, texts: list[str]) -> list[list[float]]:
        load_dotenv()
        api_key = require_env(os.environ, "GEMINI_API_KEY")
        model = require_env(os.environ, "GEMINI_EMBED_MODEL")
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=10_000),
        )
        resp = client.models.embed_content(
            model=model,
            contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        return [e.values for e in resp.embeddings or []]

    def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Lấy embedding với cache trong Postgres qua bảng embedding_cache (D-04, Task 4)."""
        if not texts:
            return []

        model_name = (
            getattr(self.embed, "model", None)
            or require_env(os.environ, "GEMINI_EMBED_MODEL")
        )
        hashes = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]

        # 1. Tra cứu embedding_cache trong Postgres
        cached_vectors: dict[str, list[float]] = {}
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT sha256, embedding FROM embedding_cache
                WHERE model = %s AND sha256 = ANY(%s)
                """,
                (model_name, list(set(hashes))),
            )
            for h, vec in cur.fetchall():
                if isinstance(vec, str):
                    vec_clean = [float(x) for x in vec.strip("[]").split(",") if x.strip()]
                    cached_vectors[h] = vec_clean
                elif isinstance(vec, (list, tuple)):
                    cached_vectors[h] = [float(x) for x in vec]

        # 2. Xác định các text chưa có trong cache
        missing_indices: list[int] = []
        missing_texts: list[str] = []
        for i, h in enumerate(hashes):
            if h not in cached_vectors:
                missing_indices.append(i)
                missing_texts.append(texts[i])

        # 3. Gọi embedder cho các text còn thiếu
        if missing_texts:
            embed_fn = self.embed if self.embed is not None else self._default_gemini_embed
            new_vectors = embed_fn(missing_texts)
            if len(new_vectors) != len(missing_texts):
                raise RuntimeError(
                    f"embedder trả {len(new_vectors)} vector cho {len(missing_texts)} câu"
                )

            with self.conn.cursor() as cur:
                missing_hashes = [hashes[i] for i in missing_indices]
                for _text_val, h, vec in zip(
                    missing_texts, missing_hashes, new_vectors, strict=True
                ):
                    cur.execute(
                        """
                        INSERT INTO embedding_cache (model, sha256, embedding)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (model, sha256) DO NOTHING
                        """,
                        (model_name, h, vec),
                    )
                    cached_vectors[h] = vec

        return [cached_vectors[h] for h in hashes]

    def ingest(self, page: Page, *, tracer: Any = None) -> IngestResult:
        chash = hashlib.sha256(page.text.strip().encode("utf-8")).hexdigest()

        # Kiểm tra nội dung trùng
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, suspicious FROM chunks WHERE content_hash = %s",
                (chash,),
            )
            existing = cur.fetchall()
            if existing:
                susp = sum(1 for row in existing if row[1])
                if susp > 0 and tracer is not None:
                    tracer.log(
                        "decision",
                        action="flag_suspicious",
                        reason="Phát hiện chỉ dẫn nghi vấn cho AI trong nội dung trang (trùng lặp)",
                        url=page.url,
                        chunks=susp,
                    )
                return IngestResult(url=page.url, chunks=0, suspicious=susp, duplicate=True)

        chunks = chunk_page(page)
        suspicious_count = 0
        if chunks:
            texts = [c.text for c in chunks]
            vectors = self._get_embeddings(texts)

            with self.conn.cursor() as cur:
                for c, vec in zip(chunks, vectors, strict=True):
                    if c.suspicious:
                        suspicious_count += 1
                    unacc = remove_accents(c.text)
                    cur.execute(
                        """
                        INSERT INTO chunks (
                            id, url, domain, title, published_at, fetched_at, trust_tier,
                            text, content_hash, suspicious, tsv, embedding
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            to_tsvector('simple', %s), %s
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            url = EXCLUDED.url,
                            domain = EXCLUDED.domain,
                            title = EXCLUDED.title,
                            published_at = EXCLUDED.published_at,
                            fetched_at = EXCLUDED.fetched_at,
                            trust_tier = EXCLUDED.trust_tier,
                            text = EXCLUDED.text,
                            content_hash = EXCLUDED.content_hash,
                            suspicious = EXCLUDED.suspicious,
                            tsv = EXCLUDED.tsv,
                            embedding = EXCLUDED.embedding
                        """,
                        (
                            c.id, c.url, c.domain, c.title, c.published_at, c.fetched_at,
                            c.trust_tier, c.text, chash, c.suspicious, unacc, vec
                        ),
                    )

        if suspicious_count > 0 and tracer is not None:
            tracer.log(
                "decision",
                action="flag_suspicious",
                reason="Phát hiện chỉ dẫn nghi vấn cho AI trong nội dung trang",
                url=page.url,
                chunks=suspicious_count,
            )

        return IngestResult(
            url=page.url,
            chunks=len(chunks),
            suspicious=suspicious_count,
            duplicate=False,
        )

    def get(self, chunk_id: str) -> Chunk | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, url, domain, title, published_at, fetched_at,
                       trust_tier, text, content_hash, suspicious
                FROM chunks WHERE id = %s
                """,
                (chunk_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return _row_to_chunk(row)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        query_vec = self._get_embeddings([query])[0]

        if self.mode == "vector":
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, url, domain, title, published_at, fetched_at,
                           trust_tier, text, content_hash, suspicious,
                           1 - (embedding <=> %s::vector) AS score
                    FROM chunks
                    WHERE NOT suspicious AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector ASC
                    LIMIT %s
                    """,
                    (query_vec, query_vec, k),
                )
                rows = cur.fetchall()
                return [
                    Hit(**_row_to_chunk(r).model_dump(), score=float(r[10]))
                    for r in rows
                ]

        # Mode hybrid: pgvector top 20 + full-text FTS top 20, kết hợp bằng RRF k=60
        vector_results: list[Chunk] = []
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, url, domain, title, published_at, fetched_at,
                       trust_tier, text, content_hash, suspicious
                FROM chunks
                WHERE NOT suspicious AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector ASC
                LIMIT 20
                """,
                (query_vec,),
            )
            for r in cur.fetchall():
                vector_results.append(_row_to_chunk(r))

        text_results: list[Chunk] = []
        unacc_query = remove_accents(query)
        words = re.findall(r"\w+", unacc_query)
        if words:
            ts_query = " | ".join(words)
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, url, domain, title, published_at, fetched_at,
                           trust_tier, text, content_hash, suspicious
                    FROM chunks
                    WHERE NOT suspicious AND tsv @@ to_tsquery('simple', %s)
                    ORDER BY ts_rank(tsv, to_tsquery('simple', %s)) DESC
                    LIMIT 20
                    """,
                    (ts_query, ts_query),
                )
                for r in cur.fetchall():
                    text_results.append(_row_to_chunk(r))

        # RRF k = 60
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}

        for result_list in (vector_results, text_results):
            for rank, c in enumerate(result_list, start=1):
                rrf_scores[c.id] = rrf_scores.get(c.id, 0.0) + (1.0 / (60.0 + rank))
                chunk_map[c.id] = c

        sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)
        return [
            Hit(**chunk_map[cid].model_dump(), score=rrf_scores[cid])
            for cid in sorted_ids[:k]
        ]


def ingest_miniweb(kb: KB, manifest_path: Path | None = None) -> int:
    """Nạp mọi trang trong manifest mà không qua agent, cho eval Recall@5 và Task 5, 6."""
    target = manifest_path or MANIFEST_PATH
    if not target.is_file():
        return 0
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return 0
    pages_list = data.get("pages", [])
    base_dir = target.parent
    total_chunks = 0

    for item in pages_list:
        file_rel = item.get("file")
        if not file_rel:
            continue
        fpath = base_dir / file_rel
        if not fpath.is_file():
            continue
        html_content = fpath.read_text(encoding="utf-8")
        text = (
            trafilatura.extract(
                html_content,
                include_comments=False,
                include_tables=True,
                output_format="txt",
            )
            or ""
        )
        metadata = trafilatura.extract_metadata(html_content)
        title = (metadata.title if metadata and metadata.title else "") or ""
        if not title:
            m = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
            if m:
                title = m.group(1).strip()

        page = Page(
            url=item["url"],
            final_url=item["url"],
            title=title,
            text=text,
            published_at=item.get("published_at"),
            fetched_at=item.get("fetched_at", datetime.now(UTC).isoformat()),
        )
        res = kb.ingest(page)
        total_chunks += res.chunks

    return total_chunks


def check_kb_allowlist(conn: Any) -> list[str]:
    """Các URL trong bảng chunks không qua tier_of (tiêu chí 1).

    URL brand-kit://... được bỏ qua (Quyết định 2).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT url FROM chunks")
        rows = cur.fetchall()

    invalid: list[str] = []
    for (url,) in rows:
        if url.startswith("brand-kit://"):
            continue
        if tier_of(url) is None:
            invalid.append(url)
    return invalid


def ingest_brand_kit(kb: KB, path: Path | None = None) -> int:
    """Nạp brand kit thành chunk tier brand, URL brand-kit://skyveil#<khoá> (Quyết định 2)."""
    target = path or BRAND_KIT_PATH
    if not target.is_file():
        return 0
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return 0

    now = datetime.now(UTC).isoformat()
    total_chunks = 0

    for key, val in data.items():
        if val is None or val == "":
            continue
        if isinstance(val, (dict, list)):
            text = yaml.dump(val, allow_unicode=True, sort_keys=False)
        else:
            text = str(val)

        url = f"brand-kit://skyveil#{key}"
        page = Page(
            url=url,
            final_url=url,
            title=f"Skyveil Brand Kit - {key}",
            text=text,
            published_at=None,
            fetched_at=now,
        )
        res = kb.ingest(page)
        total_chunks += res.chunks

    return total_chunks
