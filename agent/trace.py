"""Trace của mỗi lần chạy: input, output, tool call, skill invocation, lỗi, quyết định.

Mỗi sự kiện được ghi ngay vào ``traces/<run_id>.jsonl`` (một dòng JSON mỗi event)
và giữ trong bộ nhớ (``tracer.events``) để Task 7 stream qua SSE.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

EVENTS = frozenset(
    {"input", "llm_call", "tool_call", "skill_invocation", "error", "decision", "output"}
)

TRACES_DIR = Path("traces")


class Tracer:
    def __init__(self, run_id: str, *, traces_dir: Path = TRACES_DIR):
        self.run_id = run_id
        self.events: list[dict] = []
        self.path = traces_dir / f"{run_id}.jsonl"

    def log(self, event: str, **data) -> None:
        if event not in EVENTS:
            raise ValueError(f"event không hợp lệ: {event}, phải thuộc {sorted(EVENTS)}")
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **data,
        }
        self.events.append(record)
        self._write(record)

    def _write(self, record: dict) -> None:
        """Append một dòng JSON vào file JSONL. Tạo thư mục nếu chưa có."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
