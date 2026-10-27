# Báo cáo Bài tập Challenge B (Buổi 7): Compaction và Code Mode

> **Ghi chú dành cho nhóm:** Khung báo cáo dùng để chép sang Word. Các chỗ `…` điền số liệu/thông tin; các khung **[Hình N]** có sẵn câu lệnh và hướng dẫn chụp màn hình minh chứng.

**Đồ án:** GEO Content Writer Agent (SE373, Nhóm 05)  
**Sinh viên thực hiện:** …  
**Link repository:** …  
**Nhánh / Commit:** …

---

## 1. Tổng quát

Trong hệ thống Agentic AI, **Context Management** là bài toán trọng tâm. Khi xử lý tác vụ dài hoặc duyệt nhiều tài liệu lớn, context dễ bị đầy, gây tốn token và làm mô hình suy giảm khả năng tập trung (_lost in the middle_).

Bài tập Challenge B hiện thực hóa và đánh giá hai kỹ thuật:

- **Compaction (B1):** Tự động nén lịch sử thành một _structured checkpoint_ khi số token vượt ngưỡng, giúp agent duy trì mạch làm việc xuyên suốt phiên chạy dài mà không tràn context.
- **Code Mode (B2):** Agent tự viết và chạy script Python để lọc và tổng hợp dữ liệu ngay trong runtime cục bộ, chỉ đưa kết quả tóm tắt vào context thay vì nạp toàn bộ raw log.

**Kịch bản thực nghiệm:** Thử nghiệm trên `agent.trace_qa` (`Trace Analyst`), agent phụ phân tích 22 file trace JSONL thực tế từ hệ thống viết bài GEO (lưu tại `traces/samples/challenge-b/`).

---

## 2. Thiết kế

### 2.1. Compaction (B1)

Cài đặt cơ chế **Selective Compaction** trực tiếp trong vòng lặp chính của agent (`AgentRun`, tệp `agent/loop.py`), điều khiển qua tham số `compact_at_tokens`:

- **Cơ chế kích hoạt:** Sau mỗi vòng gọi tool, nếu `input_tokens` của lượt LLM gần nhất ≥ ngưỡng quy định (mặc định 10.000 tokens), harness sẽ chủ động nén lịch sử trước khi context chạm trần mô hình.
- **Structured Checkpoint:** Lịch sử hội thoại được nén thành một schema chuẩn hóa: `goal` (mục tiêu gốc), `constraints` (ràng buộc), `current_state` (tiến độ hiện tại), `findings` (kết quả đã tìm thấy), `failed_attempts` (hướng đi thất bại), `files` (danh sách file liên quan), `open_risks` (vấn đề chưa giải quyết), và `next_action` (bước làm tiếp theo).
- **Chiến lược chọn lọc (Selective Compaction):**
  - _Giữ lại:_ Mục tiêu gốc, quyết định quan trọng, ràng buộc và lỗi chưa xử lý.
  - _Rút gọn:_ Output dài của tool được tóm tắt thành các kết luận chính.
  - _Loại bỏ:_ Log trùng lặp, thử nghiệm đã kết luận, và dữ liệu có thể đọc lại khi cần.
- **Trạng thái sau nén:** Lịch sử chỉ còn 2 message: yêu cầu gốc và checkpoint. Dữ liệu quan sát (`observations`) dùng để kiểm chứng trích dẫn được giữ nguyên vẹn.
- **Fail-safe & Tracing:** Checkpoint bắt buộc qua bước validate schema (`goal` và `next_action` không rỗng); nếu lỗi, hệ thống giữ nguyên lịch sử cũ để chạy tiếp. Mỗi lần nén đều ghi event `decision` (`action="compact"`), lưu số token trước/sau và nội dung checkpoint.

### 2.2. Code Mode (B2)

Với tập dữ liệu nhiều file, thay vì đọc từng file vào context, LLM chỉ gọi một tool duy nhất: `run_code`.

- **Cơ chế hoạt động:** Model tự viết một đoạn script Python gọi các hàm tiện ích (`tools.list_traces()`, `tools.read_trace()`), tự lặp và tính toán thống kê trong runtime. Model chỉ nhận lại phần dữ liệu được `print` ra stdout.
- **Rào chắn an toàn (Sandbox & Constraints):**
  - Code chạy trong subprocess riêng, timeout tự ngắt sau 15 giây.
  - Giới hạn thư viện: Chỉ cho phép import `json`, `re`, `collections`, `itertools`, `statistics`, `math`, `datetime`, `fnmatch`.
  - Chặn hoàn toàn các hàm nguy hiểm: Không có `open`, `eval`, `exec`.
  - Bảo vệ bí mật: Biến môi trường của subprocess bị lọc sạch API key.
  - Giới hạn output: `stdout` bị cắt tối đa ở 4.000 ký tự.

---

## 3. Kết quả thực nghiệm

### 3.1. B2: So sánh Code Mode và Native Mode

Cùng một câu hỏi tổng hợp trên 7 file trace được giao cho agent xử lý ở cả hai chế độ:

- **Câu hỏi B2:** _"Trong các run eval-full-brief-\*, run nào phải repair nhiều nhất và mỗi lần repair vì lỗi gì? Loại lỗi validation nào lặp lại nhiều nhất?"_
- **Ground Truth** (tính bằng code ở mục 3.3):
  - Run repair nhiều nhất: `eval-full-brief-3a4ca2cb` (repair 2 lần: lần 1 do navigational < 15%, lần 2 do nhắc brand > 10%).
  - Lỗi lặp lại nhiều nhất: _"câu trùng nghĩa"_ (2 lần, tại `eval-full-brief-11c3d7c8` và `eval-full-brief-f47fca29`).

| Chế độ                          | Số lượt LLM | Input tokens | Output tokens | Độ chính xác                                                                     |
| :------------------------------ | :---------: | :----------: | :-----------: | :------------------------------------------------------------------------------- |
| **Native** (gọi tool từng file) |      7      |    58.219    |      825      | **Một phần:** Đúng run 3a4ca2cb, sai lỗi lặp nhiều nhất (dừng đọc sau 4/7 file). |
| **Code Mode** (`run_code`)      |      3      |    2.548     |      635      | **Chính xác:** Đúng trọn vẹn cả hai ý, đọc đủ 7 file.                            |

_(Số liệu chạy ngày 27/10/2026 với `TRACE_QA_MODEL=gemini-3.1-flash-lite`, run `3dec96de…` và `080c6010…`)._

**Nhận xét:** Code Mode dùng ít hơn khoảng **23 lần input tokens** và chỉ cần 3 lượt LLM thay vì 7. Ở chế độ Native, mỗi file log nạp vào làm context tăng ~2.500-4.500 tokens, và agent dừng sớm sau 4 file dù prompt yêu cầu đọc hết nhóm. Ở Code Mode, script duyệt cả 7 file ngay trong runtime nên đưa ra kết luận đầy đủ và chính xác.

> **Trước khi chạy các lệnh dưới (PowerShell, từ gốc repo):** kích hoạt virtualenv bằng `.\.venv\Scripts\Activate.ps1` để lệnh `python` trỏ vào `.venv`. Không kích hoạt thì thay `python` bằng `.\.venv\Scripts\python`.

> **[Hình 1: B2 - Chế độ Native]**
>
> - Lệnh chạy: `python -m agent.trace_qa "<câu hỏi B2>" --mode native --compact-at 0`
> - Chụp: Bảng thống kê token in ra terminal, cột `input` tăng lũy tiến sau mỗi lượt `read_trace` và dòng `Tổng`.
> - Chú thích: _"Chế độ Native: Mỗi file log thô đi vào context khiến input tokens tăng theo từng file đọc."_

> **[Hình 2: B2 - Chế độ Code Mode]**
>
> - Lệnh chạy: `python -m agent.trace_qa "<câu hỏi B2>" --mode code`
> - Chụp: Bảng token (ít lượt, input nhỏ) và câu trả lời. Ảnh phụ: đoạn code model viết trong file trace `traces/<run_id>.jsonl` (tìm `"name": "run_code"`).
> - Chú thích: _"Chế độ Code Mode: Agent viết script đọc 7 file trong runtime, chỉ kết quả tổng hợp quay về context."_

---

### 3.2. B1: Phiên làm việc dài áp dụng Compaction

Đánh giá khả năng nén context khi điều tra lỗi qua nhiều nhóm trace khác nhau:

- **Câu hỏi B1:** _"Điều tra các run eval-full-brief-\*, eval-no-persona-\* và eval-overclaim-\*: run nào gặp llm_error, nguyên nhân là gì, và trước lỗi đó run đã phải repair những lỗi validation nào?"_
- **Ground Truth:**
  - `eval-full-brief-3a4ca2cb`: `ConfigError` (thiếu `GEMINI_EMBED_MODEL`); trước đó repair 2 lần (navigational < 15%, nhắc brand > 10%).
  - `eval-no-persona-ffbfa799`: `429 RESOURCE_EXHAUSTED` khi gọi embedding; trước đó repair 2 lần (câu trùng nghĩa).
  - `eval-overclaim-746deca6`: `429 RESOURCE_EXHAUSTED` khi gọi embedding; không repair lần nào.

| Chỉ số                                       |                     Giá trị thực tế                      |
| :------------------------------------------- | :------------------------------------------------------: |
| **Ngưỡng compact (`--compact-at`)**          |                 10.000 tokens (mặc định)                 |
| **Số lần compact trong phiên**               |                          2 lần                           |
| **Input tokens trước → sau compact (Lần 1)** |             14.087 → 860 tokens (giảm 93.9%)             |
| **Input tokens trước → sau compact (Lần 2)** |            15.041 → 1.038 tokens (giảm 93.1%)            |
| **Tổng lượt LLM / Tổng input tokens**        |                 15 lượt / 110.040 tokens                 |
| **Độ chính xác câu trả lời cuối**            | **Chính xác:** Tìm đủ 3 run lỗi và đúng mọi nguyên nhân. |

_(Số liệu đo từ run `be1c159b…` ngày 27/10/2026)._

**Nhận xét:** Sau lần compact thứ hai, checkpoint ghi đúng `open_risks` là hai file chưa kiểm (`ffbfa799`, `a84d0745`) và đặt `next_action` là đọc nốt. Lượt kế tiếp, agent đọc đúng hai file này rồi trả lời.  
_Lưu ý:_ Trường `files` trong checkpoint lần 2 đã liệt kê cả hai file chưa đọc, cho thấy checkpoint do LLM sinh ra vẫn có thể gặp sai lệch nhỏ, cần kiểm soát thêm bằng code harness.

> **[Hình 3: B1 - Thời điểm nén context]**
>
> - Lệnh chạy: `python -m agent.trace_qa "<câu hỏi B1>" --mode native`
> - Chụp: Dòng `[compact] <trước> → <sau> tokens` và nội dung checkpoint YAML ngay dưới (`goal`, `findings`, `failed_attempts`, `next_action`).
> - Chú thích: _"Context vượt ngưỡng: Harness nén lịch sử thành structured checkpoint, input tokens giảm hơn 90% ở lượt kế tiếp."_

> **[Hình 4: B1 - Câu trả lời sau khi nén]**
>
> - Lệnh chạy: Cùng lệnh Hình 3, phần cuối màn hình.
> - Chụp: Các lượt sau dòng `[compact]` (agent tiếp tục đọc nốt file theo `next_action`) và câu trả lời cuối cùng kèm Evidence.
> - Chú thích: _"Sau khi nén, agent tiếp tục đúng hướng điều tra và trả lời khớp Ground Truth."_

> **[Hình 5: B1 - Trace log của sự kiện Compaction]**
>
> - Lệnh chụp: Mở `traces/<run_id>.jsonl` trong VS Code, tìm `"action": "compact"`.
> - Chụp: Dòng event `decision` chứa `input_tokens_before`, `messages_before`, `messages_after` và `checkpoint`.
> - Chú thích: _"Sự kiện nén được ghi trace đầy đủ, tra lại được trạng thái bộ nhớ agent đã giữ."_

---

### 3.3. Script tính Ground Truth

Đoạn script Python độc lập dùng để quét 22 file trace mẫu và xuất ra đáp án đối chiếu:

```python
import json
from pathlib import Path

D = Path("traces/samples/challenge-b")
events = lambda p: [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

# B2: Số lần repair và lỗi của từng run eval-full-brief
for p in sorted(D.glob("eval-full-brief-*.jsonl")):
    repairs = [e["error"][:60] for e in events(p) if e.get("action") == "repair"]
    print(p.stem, repairs)

# B1: Run gặp llm_error, nguyên nhân và các lần repair trước đó
for pattern in ("eval-full-brief-*", "eval-no-persona-*", "eval-overclaim-*"):
    for p in sorted(D.glob(pattern + ".jsonl")):
        errors = [e["message"][:80] for e in events(p) if e.get("reason") == "llm_error"]
        if errors:
            repairs = [e["error"][:50] for e in events(p) if e.get("action") == "repair"]
            print(p.stem, errors, repairs)
```

---

### 3.4. Kiểm thử tự động

Bộ test tự động dùng `pytest` với mock LLM (không tốn quota API), bao phủ toàn bộ logic nén và chạy code:

- **Compaction:** Kiểm tra kích hoạt đúng ngưỡng token, bảo toàn task gốc và `observations`, cơ chế fail-safe khi checkpoint lỗi.
- **Code Mode:** Kiểm tra chặn import trái phép/hàm `open`, ngắt vòng lặp vô hạn, không để lộ API key.

> **[Hình 6: Test suite vượt qua toàn bộ]**
>
> - Lệnh chạy: `pytest tests/test_compaction.py tests/test_code_mode.py tests/test_traces.py tests/test_trace_qa.py -v`
> - Chụp: Danh sách test case màu xanh và dòng tổng kết `passed`.
> - Chú thích: _"Bộ test tự động đảm bảo độ ổn định của Compaction và tính an toàn của Code Mode."_

---

## 4. Giới hạn và hướng phát triển

1. **Sandboxing cho Code Mode:** `run_code` hiện tại mới dùng rào chắn cấp ứng dụng (allowlist/denylist trên subprocess), chưa phải sandbox an toàn cấp OS (code vẫn có thể vượt rào qua `__subclasses__`). Khi triển khai production, cần container Docker cô lập, ngắt mạng, filesystem chỉ đọc và giới hạn CPU/RAM.
2. **Độ trễ nhận diện ngưỡng nén:** Compaction kích hoạt theo `input_tokens` của lượt gọi trước đó (trước khi nhận kết quả tool). Nếu tool trả về dữ liệu quá lớn, context có thể vượt ngưỡng thêm một lượt. Nhóm đã hạ ngưỡng mặc định từ 20.000 xuống 10.000 tokens dựa trên số liệu thực tế.
3. **Hiện tượng ảo giác trong Checkpoint:** Checkpoint do LLM viết vẫn có thể bỏ sót chi tiết hoặc đánh dấu file chưa đọc. Cần bổ sung rule kiểm tra cứng bằng code harness để đối chiếu checkpoint với lịch sử gọi tool.
4. **Code Mode phụ thuộc vào việc model biết schema dữ liệu:** Ở một lần chạy, code do model viết đọc lý do repair bằng `event.get("reason")`, trong khi trace lưu ở trường `"error"`, nên mọi lý do đều ra `'unknown'`. Code vẫn chạy không lỗi, nên harness không tự phát hiện được. Nhóm đã sửa bằng cách ghi rõ tên trường trong system prompt. Hướng tốt hơn là cho `read_trace` trả về schema có kiểu, hoặc yêu cầu model in thử một event mẫu trước khi tổng hợp.
5. **Ảnh hưởng tới Prompt Caching:** Compaction thay đổi prefix của hội thoại nên sẽ làm mất cache ở lượt ngay sau khi nén. Cần đo lường thêm sự đánh đổi giữa tiết kiệm token qua nén và chi phí mất Prompt Caching.
