"""Tool lọc trùng prompts: dùng embedding của Gemini (GEMINI_EMBED_MODEL) và cosine similarity."""

import math
import os
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field

from agent.tools import Tool

load_dotenv()


class DedupePromptsArgs(BaseModel):
    prompts: list[str] = Field(
        ...,
        description="Danh sách các câu prompt cần kiểm tra và lọc bỏ trùng lặp",
    )
    threshold: float = Field(
        default=0.9,
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


def default_gemini_embedder(texts: list[str]) -> list[list[float]]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Thiếu biến môi trường GEMINI_API_KEY")

    model = os.getenv("GEMINI_EMBED_MODEL")
    if not model:
        raise ValueError("Thiếu biến môi trường GEMINI_EMBED_MODEL")

    client = genai.Client(api_key=api_key)
    response = client.models.embed_content(model=model, contents=texts)
    embeddings = response.embeddings or []
    return [e.values for e in embeddings]


def create_dedupe_tool(
    embedder: Callable[[list[str]], list[list[float]]] = default_gemini_embedder,
) -> Tool:
    def dedupe_fn(args: DedupePromptsArgs) -> dict[str, Any]:
        if not args.prompts:
            return {"kept": [], "dropped": []}

        vectors = embedder(args.prompts)
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
            "Lọc bỏ các câu prompt trùng lặp hoặc có ngữ nghĩa gần giống nhau. "
            "Dùng embedding và độ tương đồng cosine similarity với ngưỡng threshold. "
            "Trả về danh sách index các câu được giữ ('kept') và các câu bị bỏ ('dropped')."
        ),
        args_model=DedupePromptsArgs,
        fn=dedupe_fn,
    )


dedupe_prompts = create_dedupe_tool()
