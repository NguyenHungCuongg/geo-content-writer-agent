# Báo cáo Challenge B (Buổi 7): Compaction và Code Mode

> Khung báo cáo để chép sang Word. Các ô `…` và các khung **[Hình N]** là chỗ nhóm điền số liệu và dán ảnh chụp. Mỗi khung hình ghi sẵn lệnh cần chạy (từ gốc repo, sau khi `.env` đã có key) và phần màn hình cần chụp.

**Đồ án:** GEO Content Writer Agent (SE373, đề tài 04)
**Link repo:** …
**Nhánh / commit:** …

## 1. Mục tiêu

- **B1, Compact:** phiên làm việc dài được nén khi context vượt ngưỡng. Sau khi nén, agent vẫn nhớ lỗi đang điều tra, những gì đã thử, bước tiếp theo, và trả lời đúng.
- **B2, Code Mode:** agent trả lời câu hỏi trên nhiều file log mà raw log không đi vào context. So sánh input tokens (đo qua `usage` của Gemini) giữa cách gọi tool thông thường và Code Mode.

Cả hai được demo trên **trace analyst** (`python -m agent.trace_qa`), một agent phụ trả lời câu hỏi về các file trace JSONL mà chính agent viết bài của đồ án sinh ra. Dữ liệu là snapshot 22 file trace thật ở `traces/samples/challenge-b/`.

## 2. Thiết kế

### 2.1. Compaction (B1)

- **Ở đâu:** trong vòng lặp agent dùng chung (`AgentRun`, file `agent/loop.py`), bật bằng tham số `compact_at_tokens`. Các UC sau (UC-02/03, đọc trang web dài) bật lại được, không viết riêng cho demo.
- **Khi nào:** sau một vòng có gọi tool, nếu lượt gọi LLM vừa rồi có `input_tokens` ≥ ngưỡng thì nén. Không đợi context đầy.
- **Nén thành gì:** một *structured checkpoint* có schema, không phải bản tóm tắt hội thoại: `goal`, `constraints`, `current_state`, `findings`, `failed_attempts`, `files`, `open_risks`, `next_action`.
- **Giữ / cắt / bỏ** (selective compaction): GIỮ quyết định, lỗi chưa giải quyết, ràng buộc; RÚT GỌN output dài còn vài dòng chính; BỎ log trùng, thử nghiệm đã kết luận (ghi một dòng vào `failed_attempts`), dữ liệu đọc lại được (ghi tên vào `files`).
- **Sau khi nén:** lịch sử chỉ còn một message: task gốc nguyên văn + checkpoint. Kết quả tool dùng để kiểm trích dẫn (`observations`) không bị nén.
- **Kiểm tra sau compaction:** checkpoint phải qua validate schema, `goal` và `next_action` không rỗng; hỏng thì giữ lịch sử cũ, ghi lỗi vào trace, run vẫn chạy tiếp. Test tự động kiểm agent vẫn làm tiếp và trả kết quả đúng sau khi nén.
- **Trace:** mỗi lần nén ghi event `decision` với `action="compact"`, số token trước khi nén và nguyên checkpoint.

### 2.2. Code Mode (B2)

- Model gọi **một** tool `run_code` kèm chương trình Python. Chương trình gọi `tools.list_traces()` / `tools.read_trace(name)`, tự lặp qua các file và tổng hợp; model chỉ nhận phần được `print`.
- **Chạy ở đâu:** tiến trình Python con riêng, bị dừng sau 15 giây.
- **Giới hạn quyền:** chỉ gọi được các hàm cho phép qua `tools.*`; chỉ import được `json`, `re`, `collections`, `itertools`, `statistics`, `math`, `datetime`, `fnmatch`; không có `open`, `eval`, `exec`; môi trường của tiến trình con không chứa API key; stdout bị cắt ở 4.000 ký tự.
- Như slide đã nêu, đây chưa phải sandbox bảo mật thật (xem mục 4).

## 3. Kết quả

### 3.1. B2: cùng một câu hỏi, hai cách

**Câu hỏi B2:** "Trong các run eval-full-brief-*, run nào phải repair nhiều nhất và mỗi lần repair vì lỗi gì? Loại lỗi validation nào lặp lại nhiều nhất?"

**Đáp án đối chiếu** (tính bằng đoạn code ở mục 3.3): `eval-full-brief-3a4ca2cb` phải repair 2 lần (lần 1: intent navigational chỉ 4/32 prompt, cần ≥ 15%; lần 2: 5/32 prompt nhắc thương hiệu, tối đa 10%). Lỗi lặp nhiều nhất là "câu trùng nghĩa" (2 lần, ở `eval-full-brief-11c3d7c8` và `eval-full-brief-f47fca29`).

| Chế độ | Số lượt LLM | Tổng input tokens | Tổng output tokens | Đáp án đúng? |
|---|---|---|---|---|
| Native (gọi tool từng file) | … | … | … | … |
| Code Mode (`run_code`) | … | … | … | … |

> **[Hình 1: B2, chế độ native]**
> Lệnh: `python -m agent.trace_qa "<câu hỏi B2>" --mode native --compact-at 0`
> Chụp: bảng token in ra, cột `input` tăng dần sau mỗi lượt `read_trace`, cùng dòng `Tổng`.
> Chú thích dưới hình: "Chế độ native: mỗi file log thô đi vào context, input tokens tăng theo từng file đọc."

> **[Hình 2: B2, Code Mode]**
> Lệnh: `python -m agent.trace_qa "<câu hỏi B2>" --mode code`
> Chụp: bảng token (ít lượt, input nhỏ) và câu trả lời. Ảnh phụ: mở file trace `traces/<run_id>.jsonl` (run_id in ở dòng đầu), tìm event `"name": "run_code"` để chụp đoạn code model đã viết.
> Chú thích dưới hình: "Code Mode: model viết chương trình đọc 7 file trong runtime, chỉ kết quả tổng hợp quay về context."

### 3.2. B1: phiên dài được nén

**Câu hỏi B1:** "Điều tra các run eval-full-brief-*, eval-no-persona-* và eval-overclaim-*: run nào gặp llm_error, nguyên nhân là gì, và trước lỗi đó run đã phải repair những lỗi validation nào?"

**Đáp án đối chiếu:**
- `eval-full-brief-3a4ca2cb`: ConfigError, thiếu biến `GEMINI_EMBED_MODEL` trong `.env`; trước đó repair 2 lần (navigational dưới 15%, nhắc thương hiệu quá 10%).
- `eval-no-persona-ffbfa799`: 429 RESOURCE_EXHAUSTED khi gọi embedding; trước đó repair 2 lần, cả hai vì câu trùng nghĩa.
- `eval-overclaim-746deca6`: 429 RESOURCE_EXHAUSTED khi gọi embedding; không repair lần nào.

| Chỉ số | Giá trị |
|---|---|
| Ngưỡng compact (`--compact-at`) | … |
| Số lần compact | … |
| Input tokens ngay trước compact → lượt ngay sau | … → … |
| Câu trả lời cuối đúng đáp án? | … |

> **[Hình 3: B1, lúc compact]**
> Lệnh: `python -m agent.trace_qa "<câu hỏi B1>" --mode native`
> Chụp: dòng `[compact] <trước> → <sau> tokens` và checkpoint YAML ngay dưới (goal, findings, failed_attempts, next_action).
> Chú thích dưới hình: "Context vượt ngưỡng: harness nén lịch sử thành checkpoint có cấu trúc, input tokens giảm mạnh ở lượt kế tiếp."

> **[Hình 4: B1, câu trả lời sau compact]**
> Lệnh: cùng lệnh Hình 3, phần cuối màn hình.
> Chụp: các lượt sau dòng `[compact]` (agent đọc tiếp file còn lại theo `next_action`) và câu trả lời cuối cùng kèm Evidence.
> Chú thích dưới hình: "Sau khi nén, agent tiếp tục đúng hướng điều tra và trả lời khớp đáp án đối chiếu."

> **[Hình 5: trace của lần compact]**
> Lệnh: mở `traces/<run_id>.jsonl` của lần chạy Hình 3 trong VS Code, tìm `"action": "compact"`.
> Chụp: dòng event `decision` có `input_tokens_before`, `messages_before`, `messages_after` và `checkpoint`.
> Chú thích dưới hình: "Mỗi lần nén đều được ghi trace, tra lại được trạng thái agent đã giữ."

### 3.3. Đoạn code tính đáp án đối chiếu

```python
import json
from pathlib import Path

D = Path("traces/samples/challenge-b")
events = lambda p: [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

# B2: số lần repair và lỗi của từng run eval-full-brief
for p in sorted(D.glob("eval-full-brief-*.jsonl")):
    print(p.stem, [e["error"][:60] for e in events(p) if e.get("action") == "repair"])

# B1: run gặp llm_error, nguyên nhân, và các lần repair trước đó
for pattern in ("eval-full-brief-*", "eval-no-persona-*", "eval-overclaim-*"):
    for p in sorted(D.glob(pattern + ".jsonl")):
        errors = [e["message"][:80] for e in events(p) if e.get("reason") == "llm_error"]
        if errors:
            print(p.stem, errors, [e["error"][:50] for e in events(p) if e.get("action") == "repair"])
```

### 3.4. Kiểm thử tự động

> **[Hình 6: test xanh]**
> Lệnh: `pytest tests/test_compaction.py tests/test_code_mode.py tests/test_traces.py tests/test_trace_qa.py -v`
> Chụp: danh sách test và dòng tổng kết `passed`.
> Chú thích dưới hình: "Test dùng LLM giả (không tốn quota): kiểm compact đúng ngưỡng, giữ task gốc và observations, compact hỏng không làm hỏng run; run_code chặn import/open, dừng vòng lặp vô hạn, không lộ API key."

## 4. Giới hạn và hướng phát triển

- `run_code` chỉ là hàng rào, chưa phải sandbox: code vẫn có thể thoát qua `__globals__`/`__subclasses__` của Python. Production cần container không mạng, filesystem chỉ đọc, giới hạn CPU/RAM.
- Compaction kích hoạt theo `input_tokens` của lượt trước, nên lượt vượt ngưỡng đầu tiên vẫn đã tốn đủ token; ngưỡng cần đặt thấp hơn giới hạn thật một khoảng an toàn.
- Checkpoint do LLM viết vẫn có thể bỏ sót chi tiết; hiện chỉ kiểm schema và các trường bắt buộc. Bước tiếp: bật compaction cho UC-02/03 và thêm eval so sánh kết quả có và không có compaction (rubric K4).
- Compaction đổi prefix của prompt nên làm mất prompt cache (Buổi 7, phần III); chưa đo ảnh hưởng này.
