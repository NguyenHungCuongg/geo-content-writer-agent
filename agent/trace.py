"""Trace của mỗi lần chạy: input, output, tool call, skill invocation, lỗi, quyết định.

Bản stub: giữ sự kiện trong bộ nhớ (`tracer.events`). Task 6 ghi thêm ra traces/<run_id>.jsonl.
"""

from datetime import UTC, datetime

EVENTS = frozenset(
    {"input", "llm_call", "tool_call", "skill_invocation", "error", "decision", "output"}
)


class Tracer:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: list[dict] = []

    def log(self, event: str, **data) -> None:
        if event not in EVENTS:
            raise ValueError(f"event không hợp lệ: {event}, phải thuộc {sorted(EVENTS)}")
        self.events.append({
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **data,
        })
