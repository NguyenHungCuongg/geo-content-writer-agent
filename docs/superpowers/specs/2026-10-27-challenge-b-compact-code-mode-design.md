# Challenge B (Buổi 7): Compaction và Code Mode

Ngày: 27/10/2026. Nguồn: [Buổi 7, Challenge B](../../ref/Buoi%207%20-%20Memory,%20context%20engineering,%20prompt%20caching.md), [rubric K4](../../guide/rubic-final-project.md).

## 1. Mục đích

Thầy chấm Challenge B gồm B1 Compact (bắt buộc) và B2 Code Mode (điểm cộng). Nhóm làm cả hai, nộp **link repo** và **một báo cáo ngắn có screenshot demo**. Báo cáo do nhóm tự viết trong Word, repo chỉ cần một file `.md` mẫu (xem mục 7).

Ngoài bài tập, compaction còn là điểm đồ án: rubric K4 mức Giỏi đòi "có chiến lược compaction, giữ đủ mục tiêu, ràng buộc, trạng thái, rủi ro đang mở và bước tiếp theo; có kiểm tra sau compaction". Vì vậy compaction phải nằm ở chỗ UC-02/03 (Phase 2, có `web_search`/`fetch_url` trả trang dài) bật lên dùng lại được, không viết riêng cho bài demo.

## 2. Phương án đã chốt (phương án 3)

1. **Compaction đặt trong `AgentRun`** ([agent/loop.py](../../../agent/loop.py)), bật bằng tham số, mặc định tắt.
2. **Code Mode là một tool dùng chung** `run_code`, tạo bằng factory nhận danh sách hàm được phép gọi từ trong code.
3. **Demo trên một agent phụ mỏng, "trace analyst"**: trả lời câu hỏi về các file trace JSONL của chính đồ án. 56 file trace thật là đúng loại "nhiều file log" mà B2 yêu cầu, và việc điều tra một eval case lỗi tạo ra phiên dài cho B1.

Đã cân nhắc và loại: làm trực tiếp trong UC-01 (tối đa 8 vòng, tool trả ít dữ liệu nên compact phải hạ ngưỡng giả tạo, Code Mode không có việc gì để làm); chờ UC-02/03 (chưa có mini-web, trễ bài tập).

## 3. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu**
- B1: phiên dài được compact khi vượt ngưỡng token; sau compact agent vẫn biết lỗi đang điều tra, cách đã thử, bước tiếp, và trả lời đúng.
- B2: cùng một câu hỏi trên nhiều file log, chế độ code cho cùng đáp án với chế độ native nhưng raw log không vào context; chênh lệch input tokens đo bằng `usage` của Gemini và in ra màn hình.
- Không tốn quota khi chạy test: mọi test dùng `FakeLLM`.

**Không làm (lần này)**
- Không tích hợp vào web app; demo bằng CLI.
- Không bật compaction cho UC-01. UC-02/03 bật khi được xây.
- Không làm sandbox thật (container, seccomp). Slide đã nói runtime riêng chưa phải sandbox; ta giới hạn quyền ở mức mục 5 và ghi rõ giới hạn.
- Không làm prompt caching (Challenge C), persistent memory (Challenge A), LangGraph.
- Không thêm eval case vào `evals/` cho trace analyst; kiểm bằng pytest. Eval "kiểm tra sau compaction" của K4 sẽ làm trên UC-02/03.

**Phản mục tiêu** (chạy được nhưng vẫn là thất bại)
- Sau compaction mất task gốc hoặc ràng buộc, agent làm sai việc.
- Ở chế độ code, raw log vẫn lọt vào context (ví dụ code in nguyên file).
- `run_code` đọc được file ngoài thư mục trace, mở mạng, hoặc treo vĩnh viễn.
- Hành vi hay test của UC-01 thay đổi.
- Test gọi Gemini thật.

## 4. B1: Compaction trong `AgentRun`

**Giao diện:** `run_agent(..., compact_at_tokens: int | None = None)`. `None` là tắt; mọi lời gọi hiện có giữ nguyên hành vi.

**Khi nào compact:** ở pha hành động, sau khi đã chạy xong các tool call của một vòng (lịch sử đang kết thúc bằng kết quả tool, không cắt giữa lượt), nếu `input_tokens` của lượt LLM vừa rồi ≥ `compact_at_tokens` thì compact trước vòng kế tiếp. Dùng `input_tokens` Gemini báo về (đúng gợi ý "đo input tokens qua usage" của slide), không tự đếm token.

**Cách compact:**
- Gọi LLM một lần với lịch sử hiện tại cộng một lời dặn compact, `schema=Checkpoint`. Lời gọi này không được thêm vào `self.history`, nhưng vẫn ghi trace `llm_call` như mọi lời gọi khác.
- Lời dặn compact theo slide "Selective compaction": **KEEP** quyết định, lỗi chưa giải quyết, yêu cầu bắt buộc; **TRUNCATE** output dài còn vài dòng chính; **DROP** log trùng, thử nghiệm đã kết luận (chỉ ghi một dòng vào `failed_attempts`), dữ liệu đọc lại được.
- `Checkpoint` (Pydantic) có các trường: `goal`, `constraints: list[str]`, `current_state`, `findings: list[str]`, `failed_attempts: list[str]`, `files: list[str]` (file/nguồn đã xem và còn liên quan), `open_risks: list[str]`, `next_action`. Đây là các trường slide minh hoạ cộng thêm `constraints` và `open_risks` mà rubric K4 đòi.
- Lịch sử mới gồm **đúng một** message user: task gốc nguyên văn (lưu lại lúc khởi tạo `AgentRun`) rồi tới checkpoint dạng dễ đọc (YAML hoặc JSON thụt lề). Giữ một message vì Gemini đòi `function_response` phải đi ngay sau `function_call` tương ứng; giữ lại vài lượt cuối dễ làm hỏng thứ tự đó.
- `self.observations` (validator dùng để đối chiếu trích dẫn) **giữ nguyên**, không compact.
- Bộ đếm phát hiện lặp (`call_counts`) **được reset** sau mỗi lần compact thành công. Lý do: luật DROP bỏ dữ liệu đọc lại được, nên việc model gọi lại `read_trace` cùng file sau compact là hành vi đúng, không phải vòng lặp. Trong mỗi đoạn giữa hai lần compact vẫn phát hiện lặp bình thường; `max_iterations` vẫn giới hạn tổng số vòng. (Quyết định của người viết spec.)

**Kiểm tra sau compaction (bằng code):** checkpoint phải qua validate Pydantic, `goal` và `next_action` không rỗng. Lỗi LLM (`LLMError`) hoặc checkpoint không hợp lệ thì **không** thay lịch sử, ghi trace `error` với `reason="compaction_failed"`, và agent chạy tiếp. Compaction hỏng không được làm hỏng run.

**Chống compact liên tục:** không compact lần nữa nếu từ lần compact trước chưa có kết quả tool mới. Ngưỡng nên lớn hơn hẳn kích thước một kết quả tool đã bị cắt (mục 6).

**Trace:** sự kiện `decision` với `action="compact"`, kèm `input_tokens_before`, số message trước và sau, và nguyên checkpoint. Số token sau compact đọc ở `llm_call` kế tiếp, không cần gọi API đếm token.

## 5. B2: Code Mode, tool `run_code`

**Giao diện:** một factory trong `agent/tools/` trả về `Tool` tên `run_code`, đối số `{code: str}`. Factory nhận: module Python chứa các hàm được phép, danh sách tên hàm đó, timeout, giới hạn độ dài output. Mô tả tool (model đọc) phải liệt kê chữ ký và kiểu trả về của từng hàm `tools.*`, và dặn "chỉ `print` kết quả cuối đã tổng hợp".

**Chạy ở đâu:** trong một **tiến trình con** Python (`sys.executable -I`), nhận code qua stdin. Bị kill khi quá timeout (mặc định 15 giây, theo luật timeout của đề tài). Không chạy bằng `exec` trong tiến trình agent, vì `Tool.call` không dừng được luồng đang treo.

**Giới hạn quyền** (không phải sandbox thật, phải ghi chú `ponytail:` nêu giới hạn và hướng nâng cấp lên container):
- `import` chỉ cho phép một allowlist nhỏ các module thuần tính toán: `json`, `re`, `collections`, `itertools`, `statistics`, `math`, `datetime`, `fnmatch`.
- Bỏ `open`, `eval`, `exec`, `compile`, `input`, `breakpoint` khỏi builtins của code. Truy cập dữ liệu chỉ qua `tools.*`.
- Biến môi trường của tiến trình con không chứa secret (không truyền `GEMINI_API_KEY`).
- Chỉ stdout quay về model, cắt ở khoảng 4.000 ký tự, có cờ `truncated`. Code lỗi thì trả `ok=False` cùng vài dòng cuối traceback để model tự sửa. Không retry (lỗi code không phải lỗi tạm thời).

## 6. Trace analyst (agent demo)

**Lệnh:**
```
python -m agent.trace_qa "câu hỏi" --mode native|code [--traces-dir DIR] [--compact-at N]
```

**Dữ liệu:** `traces/` bị gitignore, nên commit một snapshot vài chục file trace thật hiện có vào `traces/samples/challenge-b/` (thư mục `traces/samples/` vốn được phép commit). `--traces-dir` mặc định trỏ vào snapshot này. Trace chỉ chứa brief hư cấu, nhưng vẫn phải soát lại trước khi commit để chắc không có secret.

**Hàm truy cập trace** (một module, dùng chung cho cả hai chế độ):
- `list_traces(pattern="*")`: tên file, số dòng, kích thước.
- `read_trace(name)`: danh sách event đã parse. Tên phải là file `.jsonl` nằm trong thư mục trace; chặn `..`, đường dẫn tuyệt đối, symlink ra ngoài.

**Chế độ native:** tool `list_traces` và `read_trace` khai báo bình thường; kết quả đi thẳng vào context (đó chính là bloat cần chứng minh). `read_trace` ở chế độ này cắt ở khoảng 30.000 ký tự cho mỗi lần gọi để giữ quota free tier, có cờ `truncated`. Compaction mặc định bật với ngưỡng đủ thấp để demo kích hoạt được trên snapshot (khoảng 20k token; người làm chỉnh theo snapshot thực tế); `--compact-at 0` tắt hẳn. `max_iterations` đủ lớn cho phiên dài (khoảng 25).

**Hai kịch bản demo chạy riêng:**
- B2 so sánh native và code chạy với **compaction tắt** (`--compact-at 0` ở lệnh native), để bảng token thể hiện đúng input tăng dần theo từng file đọc và đáp án hai bên đối chiếu được.
- B1 chạy native với compaction bật (ngưỡng mặc định).

**Chế độ code:** chỉ một tool `run_code` với `tools.list_traces` / `tools.read_trace`. `max_iterations` nhỏ (khoảng 6). Không cần compaction.

**Output:** schema `TraceAnswer { answer: str, evidence: list[str] }`, trong đó `evidence` là các run_id dùng làm căn cứ. Validator kiểm mỗi run_id có file tương ứng trong thư mục trace (kiểm bằng code, cùng tinh thần luật "mọi số liệu có nguồn").

**Model:** đọc `TRACE_QA_MODEL`, trống thì dùng `GEMINI_MODEL`. Mục đích là để nhóm tách sang model khác, có hạn mức free tier riêng, mà không ảnh hưởng UC-01 và eval. Thêm biến này (để trống, có chú thích) vào `.env.example`.

**In ra màn hình** (đây là thứ sẽ chụp cho báo cáo):
1. Run ID và đường dẫn file trace.
2. Bảng từng lượt gọi LLM: số thứ tự, tool đã gọi, `input_tokens`, `output_tokens`.
3. Mỗi lần compact: dòng `[compact] <tokens trước> → <tokens lượt sau>` và checkpoint.
4. Câu trả lời, evidence, tổng input/output tokens.

**Trace:** ghi `input` (câu hỏi, mode) và `output` như UC-01 (luật 9).

**Câu hỏi demo:** chỉ dùng dữ liệu có trong trace. Trace không ghi eval case đạt hay trượt (kết quả đó nằm ở `evals/results/*.json`, bị gitignore, không đưa vào snapshot). Dữ liệu điều tra được là các sự kiện `decision` `action="repair"` (khoảng 19 run, có nội dung lỗi validation) và `error` `llm_error`. Mỗi câu hỏi phải có đáp án đúng tính được bằng một đoạn Python thuần, ghi trong báo cáo mẫu để đối chiếu. Người làm chọn câu cụ thể sau khi xem snapshot:
- Câu cho B2: tổng hợp trên **một nhóm file** chứ không phải cả snapshot (ví dụ 5-7 file `eval-full-brief-*`), để chế độ native vừa `max_iterations` và quota free tier. Ví dụ: "trong các run eval-full-brief, run nào phải repair nhiều nhất, lỗi validation nào lặp lại nhiều nhất".
- Câu cho B1: một câu điều tra lỗi buộc agent đọc nhiều file liên tiếp, ví dụ "những lỗi validation nào khiến model phải sửa output, lần sửa thứ mấy thì qua, run nào còn gặp llm_error". Phần "lỗi đang điều tra / cách đã thử / bước tiếp" trong checkpoint là quá trình điều tra của chính agent (giả thuyết, file đã đọc, file còn phải đọc).

## 7. Báo cáo mẫu

File `docs/reports/buoi7-challenge-b.md`: khung báo cáo cho nhóm chép sang Word. Gồm: mục tiêu; thiết kế ngắn (compaction ở đâu, khi nào, giữ/bỏ gì; Code Mode chạy ở đâu, giới hạn gì); bảng kết quả token native và code (ô trống để điền); giới hạn và hướng phát triển (sandbox thật, bật cho UC-02/03).

Mỗi chỗ cần ảnh là một placeholder có: tên hình, **lệnh chính xác cần chạy**, **phần màn hình cần chụp**, chú thích dưới hình. Tối thiểu:
1. B2 chế độ native: bảng token cho thấy input tăng dần theo từng file đọc.
2. B2 chế độ code: đoạn code model đã viết (lấy từ trace) và bảng token nhỏ, cùng đáp án.
3. B1: dòng `[compact]` và checkpoint in ra.
4. B1: câu trả lời cuối sau compact, đúng với đáp án đối chiếu.
5. Trace JSONL có sự kiện `decision` `action="compact"`.
6. `pytest` xanh cho các test mục 8.

## 8. Kiểm thử (pytest, chỉ `FakeLLM`)

- Compaction: kích hoạt khi `input_tokens` ≥ ngưỡng; lịch sử còn một message chứa nguyên văn task và checkpoint; `observations` giữ nguyên; có trace `decision`/`compact`; sau compact agent chạy tiếp và finalize đúng.
- Compaction tắt mặc định: model không nhận lời gọi compact nào (các test UC-01 hiện có vẫn xanh).
- Compaction hỏng (checkpoint sai schema hoặc `LLMError`): lịch sử giữ nguyên, có trace `compaction_failed`, run vẫn xong.
- `run_code`: in đúng kết quả; vòng lặp vô hạn bị kill sau timeout; `import os` và `open(...)` bị chặn; output dài bị cắt; không gọi được hàm ngoài danh sách cho phép.
- `read_trace` từ chối `../`, đường dẫn tuyệt đối, file không phải `.jsonl`.
- Trace analyst chạy trọn ở cả hai mode với `FakeLLM` trên thư mục trace tạm; evidence trỏ tới run_id không tồn tại thì validator báo lỗi.

`ruff check .` và `pytest` phải xanh.

## 9. Tài liệu đi kèm

- Thêm D-12 vào [docs/decisions.md](../../decisions.md): compaction nằm trong `AgentRun`, trigger theo `input_tokens`, lịch sử sau compact là một message, `observations` không bị compact; Code Mode chạy trong tiến trình con với các giới hạn ở mục 5. Ghi lý do và hệ quả theo định dạng các D trước.
- `.env.example`: thêm `TRACE_QA_MODEL`.
- Không sửa roadmap: Challenge B không phải task trong roadmap Phase 1, còn `phase-2.md` chưa tồn tại.

## 10. Để người làm tự quyết

Tên module, file và hàm; chữ ký chính xác của factory `run_code`; nội dung lời dặn compact và system prompt của trace analyst; định dạng hiển thị checkpoint; cách dựng bảng in ra; ngưỡng compact cụ thể và giới hạn cắt output, miễn bám các ràng buộc ở trên; chọn những file nào vào snapshot.
