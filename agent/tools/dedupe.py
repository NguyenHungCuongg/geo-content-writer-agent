"""Tool lọc prompt trùng nghĩa: embedding của Gemini (GEMINI_EMBED_MODEL) và cosine similarity.

uc01 dùng lại tool này để kiểm trùng trên PromptSet cuối (D-11).
"""

import math
import os
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from agent.llm import require_env
from agent.schemas import MAX_SIMILARITY
from agent.tools import Tool

# Hết trước timeout 15s của tool, để luồng chạy tool tự kết thúc thay vì treo nền.
EMBED_TIMEOUT_MS = 10_000
# Giới hạn số câu trong một lần gọi embedding theo lô của Gemini.
MAX_PROMPTS = 100


class DedupePromptsArgs(BaseModel):
    prompts: list[str] = Field(
        ...,
        max_length=MAX_PROMPTS,
        description="Toàn bộ câu prompt nháp, theo thứ tự",
    )
    threshold: float = Field(
        default=MAX_SIMILARITY,
        ge=0.0,
        le=1.0,
        description=(
            "Ngưỡng độ tương đồng cosine (từ 0.0 đến 1.0). "
            "Lớn hơn hoặc bằng ngưỡng sẽ bị loại"
        ),
    )


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2, strict=True))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def cached(
    embed: Callable[[list[str]], list[list[float]]], max_size: int = 500
) -> Callable[[list[str]], list[list[float]]]:
    """Chỉ embed câu chưa gặp. Mỗi lần tự sửa, loop kiểm trùng lại cả tập dù đa số câu giữ nguyên;
    không cache thì quota embedding free tier (tính theo từng câu) hết sau vài case và trả 429."""
    # ponytail: xoá sạch khi đầy thay vì LRU; mỗi vector 3072 số ~100 KB nên 500 câu ~50 MB.
    cache: dict[str, list[float]] = {}

    def embed_cached(texts: list[str]) -> list[list[float]]:
        unique = list(dict.fromkeys(texts))
        missing = [text for text in unique if text not in cache]
        if len(cache) + len(missing) > max_size:
            cache.clear()
            missing = unique
        if missing:
            vectors = embed(missing)
            if len(vectors) != len(missing):
                raise RuntimeError(f"embedding trả {len(vectors)} vector cho {len(missing)} câu")
            cache.update(zip(missing, vectors, strict=True))
        return [cache[text] for text in texts]

    return embed_cached


def gemini_embed(texts: list[str]) -> list[list[float]]:
    load_dotenv()
    client = genai.Client(
        api_key=require_env(os.environ, "GEMINI_API_KEY"),
        http_options=types.HttpOptions(timeout=EMBED_TIMEOUT_MS),
    )
    response = client.models.embed_content(
        model=require_env(os.environ, "GEMINI_EMBED_MODEL"), contents=texts
    )
    return [e.values for e in response.embeddings or []]


default_gemini_embedder = cached(gemini_embed)


def create_dedupe_tool(
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> Tool:
    """`embedder` để trống thì dùng Gemini; test truyền embedder giả để không gọi mạng."""

    def dedupe_fn(args: DedupePromptsArgs) -> dict[str, Any]:
        if not args.prompts:
            return {"kept": [], "dropped": []}

        # Tra embedder mặc định lúc gọi, không phải lúc tạo tool, để tests/conftest.py thay được.
        vectors = (embedder or default_gemini_embedder)(args.prompts)
        if len(vectors) != len(args.prompts):
            raise RuntimeError(f"embedding trả {len(vectors)} vector cho {len(args.prompts)} câu")

        kept: list[int] = []
        dropped: list[tuple[int, int, float]] = []

        for i, vec in enumerate(vectors):
            matched = False
            for k in kept:
                sim = cosine_similarity(vec, vectors[k])
                if sim >= args.threshold:
                    dropped.append((i, k, round(float(sim), 4)))
                    matched = True
                    break
            if not matched:
                kept.append(i)

        return {"kept": kept, "dropped": dropped}

    return Tool(
        name="dedupe_prompts",
        description=(
            "Tìm các câu prompt trùng nghĩa bằng embedding và cosine similarity. "
            "Gọi sau khi nháp xong danh sách prompt và trước khi trả kết quả cuối: truyền toàn bộ "
            "câu nháp theo thứ tự, rồi viết lại cho khác ý các câu nằm trong 'dropped'. "
            "Trả về 'kept' (index các câu giữ) và 'dropped' (mỗi phần tử là "
            "[index câu bị trùng, index câu nó trùng với, cosine])."
        ),
        args_model=DedupePromptsArgs,
        fn=dedupe_fn,
    )


dedupe_prompts = create_dedupe_tool()
