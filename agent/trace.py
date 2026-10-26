"""Trace của mỗi lần chạy: input, output, tool call, skill invocation, lỗi, quyết định.

Mỗi sự kiện được giữ trong bộ nhớ (``tracer.events``, app stream qua SSE) rồi ghi ngay vào
``traces/<run_id>.jsonl`` ở gốc repo (một dòng JSON mỗi event).
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

EVENTS = frozenset(
    {"input", "llm_call", "tool_call", "skill_invocation", "error", "decision", "output"}
)

# Neo theo gốc repo, không theo thư mục đang chạy: backend phát lại trace từ đây (Task 7).
TRACES_DIR = Path(__file__).resolve().parents[1] / "traces"

log = logging.getLogger(__name__)


class Tracer:
    def __init__(self, run_id: str, *, traces_dir: Path | None = None):
        self.run_id = run_id
        self.events: list[dict] = []
        self.path = (traces_dir or TRACES_DIR) / f"{run_id}.jsonl"

    def log(self, event: str, **data) -> None:
        if event not in EVENTS:
            raise ValueError(f"event không hợp lệ: {event}, phải thuộc {sorted(EVENTS)}")
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **data,
        }
        self.events.append(record)  # trước khi ghi file: stream của app đọc từ đây
        self._write(record)

    def _write(self, record: dict) -> None:
        """Append một dòng JSON. Ghi hỏng thì chỉ cảnh báo: trace lỗi không được làm hỏng run."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            log.warning("không ghi được trace %s", self.path, exc_info=True)
