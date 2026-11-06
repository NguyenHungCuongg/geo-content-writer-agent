"""UC-02: Nghiên cứu nguồn và dựng kho tri thức có trích dẫn (Phase 2, Task 4).

Chạy thử từ dòng lệnh:
    python -m agent.uc02 --topic "sơn chống nóng mái tôn" --question "QCVN 09:2017 quy định gì?"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from typing import Self
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationInfo, model_validator

from agent.kb import KB, Citation, MemoryKB, check_citation
from agent.llm import LLM, GeminiLLM
from agent.loop import AgentStopped, run_agent
from agent.schemas import Prompt
from agent.tools.kb import kb_ingest_tool, kb_search_tool
from agent.tools.web import make_web_search_tool
from agent.trace import Tracer


class ResearchAnswer(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = []
    insufficient: bool = False


class ResearchReport(BaseModel):
    topic: str
    queries: list[str]
    answers: list[ResearchAnswer]

    @model_validator(mode="after")
    def validate_report(self, info: ValidationInfo) -> Self:
        # 1. queries có >= 3 câu khác nhau
        unique_queries = {q.strip().lower() for q in self.queries if q.strip()}
        if len(unique_queries) < 3:
            raise ValueError(
                f"queries phải có ít nhất 3 câu khác nhau (hiện có {len(unique_queries)})"
            )

        kb: KB | None = info.context.get("kb") if info.context else None

        for i, ans in enumerate(self.answers, start=1):
            # 2. Nếu insufficient=True: citations phải rỗng và answer là câu báo không đủ nguồn
            if ans.insufficient:
                if ans.citations:
                    raise ValueError(
                        f"Câu hỏi {i} ('{ans.question}'): "
                        "insufficient=True thì không được có citation"
                    )
                if "không đủ nguồn" not in ans.answer.lower():
                    raise ValueError(
                        f"Câu hỏi {i} ('{ans.question}'): insufficient=True "
                        "thì answer phải là câu báo không đủ nguồn"
                    )
                continue

            # 3. Mọi [n] trong answer phải có trong citations
            bracket_numbers = {int(n) for n in re.findall(r"\[(\d+)\]", ans.answer)}
            citation_numbers = {c.n for c in ans.citations}
            missing_citations = bracket_numbers - citation_numbers
            if missing_citations:
                raise ValueError(
                    f"Câu hỏi {i} ('{ans.question}'): [n] trong answer "
                    f"({sorted(missing_citations)}) chưa có trong danh sách citations"
                )

            # 4. Mọi citation qua check_citation nếu có kb
            if kb is not None:
                for c in ans.citations:
                    err = check_citation(c, kb)
                    if err is not None:
                        raise ValueError(
                            f"Câu hỏi {i} ('{ans.question}'): trích dẫn [{c.n}] không hợp lệ: {err}"
                        )

        return self


def format_citation(c: Citation) -> str:
    """Định dạng một trích dẫn: [n] URL "đoạn trích"."""
    return f'[{c.n}] {c.url} "{c.quote}"'


SYSTEM_PROMPT = """\
Bạn là chuyên viên nghiên cứu và xây dựng kho tri thức cho bài viết GEO.
Nhiệm vụ: nghiên cứu chủ đề và trả lời danh sách câu hỏi nghiên cứu một cách chính xác, khách quan.

Quy trình:
1. Sinh các truy vấn con (ít nhất 3 câu khác nhau) lưu vào trường queries.
2. Dùng tool web_search để tìm kiếm các trang nguồn liên quan trong allowlist.
3. Dùng tool kb_ingest để nạp các trang tiềm năng vào kho tri thức RAG.
4. Dùng tool kb_search để truy hồi các đoạn văn bản (chunks) chứa dữ liệu thực tế và trích dẫn.
5. Tổng hợp câu trả lời cho từng câu hỏi nghiên cứu:
   - Nếu câu hỏi có đủ nguồn: trả lời kèm trích dẫn dạng [n] ngay trong câu.
     Mỗi trích dẫn trỏ tới một chunk có thật, và quote là chuỗi con nguyên văn của chunk đó.
   - Nếu câu hỏi KHÔNG có nguồn trong kho: đặt insufficient = true, trả lời rõ ràng là
     "không đủ nguồn", và để danh sách citations rỗng. Tuyệt đối không được bịa số liệu.
"""


def run_uc02(
    topic: str,
    questions: list[str],
    *,
    prompts: Sequence[Prompt] = (),
    kb: KB | None = None,
    llm: LLM | None = None,
    tracer: Tracer | None = None,
) -> ResearchReport:
    """Chạy UC-02: nghiên cứu nguồn tin cậy, nạp kho tri thức và trả lời câu hỏi có trích dẫn."""
    load_dotenv()
    t = tracer or Tracer(uuid4().hex)
    kbase = kb if kb is not None else MemoryKB()
    client_llm = llm if llm is not None else GeminiLLM()

    t.log(
        "input",
        topic=topic,
        questions=questions,
        prompts=[p.model_dump() for p in prompts],
    )

    compact_env = os.getenv("COMPACT_AT_TOKENS")
    compact_at_tokens = int(compact_env) if compact_env and compact_env.isdigit() else None

    tools = [
        make_web_search_tool(),
        kb_ingest_tool(kbase, tracer=t),
        kb_search_tool(kbase),
    ]

    task_desc = (
        f"Chủ đề nghiên cứu: {topic}\n"
        f"Danh sách câu hỏi nghiên cứu cần trả lời:\n"
        + "\n".join(f"- {q}" for q in questions)
    )
    if prompts:
        task_desc += (
            "\n\nNhóm prompt mục tiêu cần lưu ý (từ brand profile / UC-01):\n"
            + "\n".join(f"- [{p.intent}] {p.text}" for p in prompts)
        )

    try:
        agent_result = run_agent(
            client_llm,
            system=SYSTEM_PROMPT,
            task=task_desc,
            output_model=ResearchReport,
            tools=tools,
            validation_context={"kb": kbase},
            tracer=t,
            max_iterations=15,
            compact_at_tokens=compact_at_tokens,
        )
        report = agent_result.output  # type: ignore
        t.log("output", report=report.model_dump())
        return report
    except AgentStopped as e:
        t.log("error", reason=e.reason, message=str(e))
        raise
    except Exception as e:
        t.log("error", reason="internal_error", message=str(e))
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="UC-02: Nghiên cứu nguồn và dựng kho tri thức")
    parser.add_argument("--topic", required=True, help="Chủ đề nghiên cứu")
    parser.add_argument(
        "--question",
        dest="questions",
        action="append",
        required=True,
        help="Câu hỏi nghiên cứu (có thể truyền nhiều lần)",
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    try:
        report = run_uc02(args.topic, args.questions)
    except Exception as e:
        print(f"Lỗi UC-02: {e}", file=sys.stderr)
        return 1

    print(f"\nBÁO CÁO NGHIÊN CỨU: {report.topic}")
    print(f"Truy vấn con đã thực hiện ({len(report.queries)}):")
    for q in report.queries:
        print(f"  • {q}")
    print("\nCÂU TRẢ LỜI:")
    for ans in report.answers:
        print(f"\nQ: {ans.question}")
        if ans.insufficient:
            print(f"A: [Không đủ nguồn] {ans.answer}")
        else:
            print(f"A: {ans.answer}")
            if ans.citations:
                print("Trích dẫn:")
                for c in ans.citations:
                    print(f"  {format_citation(c)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
