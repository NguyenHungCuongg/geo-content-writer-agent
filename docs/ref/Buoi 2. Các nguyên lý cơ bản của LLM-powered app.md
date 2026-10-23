# Buổi 02 – Các nguyên lý cơ bản của LLM-powered app

*Xây dựng ứng dụng và tích hợp mô hình ngôn ngữ lớn*

## Nội dung

1. LLM-Powered App
2. Prompt và Context Engineering
3. Structured Output
4. Function Calling và Tool Use
5. Bước đệm sang AI agent
6. Tổng kết

---

## 1. LLM-Powered App

**LLM-powered app** là phần mềm gọi LLM để xử lý input và sử dụng output trong luồng xử lý của ứng dụng.

### Ví dụ: ứng dụng Issue Triage

- Input: mô tả một lỗi trong hệ thống thanh toán.
- Ứng dụng cần phân loại issue theo mức **P0, P1, P2 hoặc P3**.
- Trong ví dụ này, P0 nghiêm trọng nhất, P3 ít nghiêm trọng nhất; thực tế có thể khác giữa các tổ chức.

**Output ban đầu** của model có thể là một đoạn văn:

> "Đây có vẻ là sự cố nghiêm trọng ở luồng thanh toán và nên được ưu tiên xử lý ngay. Có thể xếp P0 hoặc P1 tùy phạm vi ảnh hưởng."

- Con người có thể hiểu output này.
- Ứng dụng **không thể** xử lý thông tin mơ hồ như vậy.

### LLM API

- Ứng dụng gửi một API request có cấu trúc tới model.
- Request thường chứa: `model`, `messages`, generation parameters, và có thể kèm schema hoặc tool.
- Response thường chứa: output, lý do kết thúc (`stop reason`), tool call hoặc structured data nếu có, và thông tin `usage`.

### Messages

- **system / developer:** instruction nền cho model.
- **user:** input hoặc yêu cầu từ người dùng hay ứng dụng.
- **assistant:** output trước đó của model trong cùng hội thoại.
- Các API có thể hỗ trợ thêm message cho tool result hoặc nội dung khác.

### Token

- Text được tokenizer chuyển thành token trước khi model xử lý.
- Một từ có thể tương ứng với một hoặc nhiều token tùy tokenizer và ngôn ngữ.
- Số token ảnh hưởng đến context window, chi phí và thời gian xử lý.

**Demo tokenizer** – cùng một nội dung tương đương bằng tiếng Anh và tiếng Việt:

| Tokenizer | EN | VI | Tỉ lệ VI/EN |
|---|---|---|---|
| cl100k_base | 93 | 228 | 2,45× |
| o200k_base | 87 | 142 | 1,63× |

- Không nên ước tính token bằng `len(text.split())`.
- Đổi model hoặc tokenizer có thể làm thay đổi chi phí dù nội dung không đổi.

### Context window

- Context window là tổng lượng token model có thể xử lý trong một lần gọi.
- Context gồm: instruction, examples, user input, history, dữ liệu bổ sung và output đang được sinh.
- Vượt giới hạn kỹ thuật có thể làm request thất bại hoặc output bị giới hạn.

**Context chưa đầy vẫn có vấn đề:**

1. **Lost in the middle:** model có thể sử dụng kém thông tin ở giữa context so với đầu và cuối.
2. **Context rot:** hiệu năng có thể giảm khi input ngày càng dài và nhiều nhiễu hoặc distractor, dù vẫn còn trong giới hạn kỹ thuật.

### Chi phí token

- Mỗi lần gọi model, phần context gửi vào lại được xử lý hoặc tính phí (có thể theo cơ chế cache của nhà cung cấp).
- Với workflow nhiều bước, cùng một context có thể được gửi lại nhiều lần.

**Ví dụ task 10 bước:** mỗi bước có 3.000 token nền, mỗi bước thêm trung bình 500 token lịch sử mới. Tổng input là tổng token của 10 lần gọi, không phải token của riêng bước cuối.

Bảng giá tham khảo được trình bày theo đơn vị USD / 1 triệu token, gồm giá input, cached input và output của các model trong slide (không cố định, chỉ để minh hoạ cách so sánh).

### Prompt caching

- Một số API cache phần prompt hoặc context lặp lại giữa nhiều request.
- Prompt caching giảm chi phí hoặc độ trễ khi prefix giống nhau được dùng nhiều lần.
- **Cache không làm model hiểu task tốt hơn**; nó chỉ tối ưu phần xử lý lặp lại.

### Generation parameters

- **temperature** và **top_p** ảnh hưởng cách model chọn token tiếp theo.
  - Temperature thấp (0–0,2): chọn phương án có xác suất cao hơn → ổn định, ít sáng tạo.
  - Temperature cao (0,8–1,2): dễ chọn phương án ít chắc chắn hơn → đa dạng, nhưng cũng dễ lệch.
  - `top_p`: giới hạn tập token được đưa vào tập ứng viên.
- **max_tokens** (hoặc tham số tương đương) giới hạn độ dài output.
- Không phải model hay API nào cũng hỗ trợ cùng một tập generation parameters.

---

## 2. Prompt và Context Engineering

### Prompt engineering

Prompt ngắn: `Phân loại issue này: {issue}`

Model chưa biết: dùng thang phân loại nào; cần giải thích hay chỉ trả nhãn; có được suy đoán khi thiếu dữ liệu không; P0 khác P1 thế nào.

**Cấu trúc prompt:**

| Thành phần | Vai trò | Ví dụ Issue Triage |
|---|---|---|
| Role / persona | Model đang đóng vai gì | Kỹ sư phân loại sự cố |
| Context | Hệ thống nào đang gặp vấn đề | API thanh toán đang chạy |
| Yêu cầu | Model cần làm gì | Phân loại mức độ nghiêm trọng |
| Input | Dữ liệu cần xử lý | Nội dung issue |
| Ràng buộc | Điều model không được tự suy đoán | Thiếu dữ liệu phải báo thiếu |
| Các bước | Cách chia task khi cần | Xác định ảnh hưởng → gán mức |
| Output | Kết quả mong muốn | Severity + lý do |
| Ví dụ | Mẫu tham khảo | Issue đã gán nhãn đúng |

**Prompt có cấu trúc** dùng thẻ XML để tách instruction khỏi dữ liệu:

```xml
<role>
Bạn là kỹ sư phụ trách phân loại sự cố trên hệ thống đang chạy.
</role>
<task>
Phân loại mức độ nghiêm trọng theo P0/P1/P2/P3.
Không suy đoán nếu dữ liệu chưa đủ.
</task>
<input>
{issue_text}
</input>
<output>
Trả severity và lý do ngắn gọn.
</output>
```

- Thẻ XML giúp tách instruction khỏi dữ liệu rõ hơn.
- Prompt dài hơn không tự động làm model tốt hơn.

### In-context learning

Dạy model tác vụ mới bằng context của prompt, **không thay đổi trọng số**.

| Kỹ thuật | Số ví dụ | Chi phí token |
|---|---|---|
| Zero-shot | 0 | Thấp nhất |
| One-shot | 1 | Thấp |
| Few-shot | 2–5 | Trung bình |
| CoT | Ví dụ + lập luận | Cao nhất |

- **Zero-shot:** chỉ đưa instruction và dữ liệu đầu vào.
- **One-shot / few-shot:** thêm ví dụ mẫu để định hình cả quy tắc lẫn cấu trúc output.

**Few-shot prompting:**

```
Example 1
Input: Trang chủ sai màu icon
Output: P3
Example 2
Input: Không user nào thanh toán được
Output: P0

Now classify:
{issue}
```

- Few-shot đưa ví dụ input-output vào context của request hiện tại; trọng số model không đổi.

**Trade-offs của few-shot:**

- *Hữu ích:* hệ thống phân loại riêng; format hoặc edge case khó mô tả; cần minh hoạ boundary case.
- *Phản tác dụng:* ví dụ làm context quá dài; ví dụ thiên lệch về một label; ví dụ lỗi thời; chỉ dùng để ép JSON trong khi đã có schema phù hợp hơn.

### Chain of Thought (CoT)

Yêu cầu model trình bày các bước lập luận trung gian trước khi cho kết quả.

Ví dụ bài toán "cộng các số palindrome trong dãy 13, 1331, 121, 73, 99, 56, 232, 7":
- **Zero-shot:** output 1691 – *bỏ sót 99, sai.*
- **CoT** ("Hãy làm theo từng bước: 1) tìm tất cả số palindrome, 2) cộng các số tìm được"): output 1331 + 121 + 99 + 232 + 7 = **1790 – đúng.**

- Chia nhỏ bài toán hiệu quả hơn việc chỉ thêm ví dụ mẫu.
- Các model reasoning mới tự suy luận từng bước, giảm sự phụ thuộc vào mẹo CoT thủ công.

### Prompt template

```python
from langchain_core.prompts import ChatPromptTemplate

triage_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "Bạn là kỹ sư phụ trách phân loại sự cố. "
        "Phân loại issue theo P0/P1/P2/P3. "
        "Nếu thiếu dữ liệu, nói rõ thiếu dữ liệu."
    ),
    ("user", "{issue_text}"),
])
```

- Prompt có biến đầu vào có tên, tái sử dụng được.
- Prompt có thể được versioning, review và test cùng source code.

### Prompt engineering và context engineering

| | Prompt engineering | Context engineering |
|---|---|---|
| Câu hỏi | Thiết kế cách mô tả task trong một model call | Quyết định thông tin nào được đưa vào context |
| Thành phần | Instruction, examples, output yêu cầu | File, history, retrieval result, tool result |
| Trọng tâm | Cách hỏi | Dữ liệu được nạp |

---

## 3. Đầu ra có cấu trúc (Structured Output)

Quay lại output đầu buổi: câu trả lời "Đây là vấn đề nghiêm trọng, có thể P0 hoặc P1 tùy phạm vi ảnh hưởng" có thể hợp lý với người đọc nhưng **không tạo ra một giá trị severity ổn định** cho ứng dụng.

- Regex hoặc substring không giải quyết triệt để vấn đề:

```python
if "P0" in response:
    notify_incident_team()
```

- Ví dụ model trả về "Văn bản này nên được phân loại là tech vì nó bàn về một sản phẩm công nghệ." Với người đọc, câu giải thích này có thể hữu ích. Nhưng với đoạn code `if result == "tech"`, output đó **không đúng interface mong đợi**. Ứng dụng cần đúng giá trị `tech`.

**Nguyên tắc:**

- KHÔNG: model → prose → đoán kiểu → code
- NÊN: model → dữ liệu có cấu trúc → code

**Structured output** yêu cầu model trả output theo một cấu trúc xác định trước. JSON là format phổ biến vì dễ truyền qua API và xử lý bằng mã nguồn.

### JSON Schema cho IssueTriage

```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["classified", "insufficient_data", "out_of_scope"]
    },
    "severity": {
      "type": ["string", "null"],
      "enum": ["P0", "P1", "P2", "P3", null]
    },
    "component": {"type": ["string", "null"]},
    "needs_urgent_response": {"type": "boolean"},
    "reason": {"type": "string"}
  },
  "required": ["status", "severity", "component", "needs_urgent_response", "reason"],
  "additionalProperties": false
}
```

- `enum` thu hẹp tập giá trị hợp lệ.
- `required` xác định field bắt buộc.
- `additionalProperties: false` từ chối field không khai báo.
- Schema nên có trạng thái hợp lệ cho trường hợp không đủ dữ liệu (`insufficient_data`, `severity: null`).

### Pydantic

```python
from typing import Literal
from pydantic import BaseModel, Field

class IssueTriage(BaseModel):
    status: Literal["classified", "insufficient_data", "out_of_scope"]
    severity: Literal["P0", "P1", "P2", "P3"] | None = None
    component: str | None = None
    needs_urgent_response: bool = False
    reason: str = Field(description="Lý do ngắn gọn dựa trên dữ liệu issue")
```

- Kiểu dữ liệu và ràng buộc nằm gần application code.
- Có runtime validation và có thể sinh JSON Schema.

**Cách khai báo schema trong Python:**

| Cách | Runtime validation | Khi phù hợp |
|---|---|---|
| Pydantic `BaseModel` | Có | Cần kiểm tra dữ liệu rõ ràng |
| `TypedDict` | Không | Cần type hint nhẹ |
| `dataclass` | Nhẹ | Cần cấu trúc Python đơn giản |
| JSON Schema | Tùy validator | Cần liên thông với hệ thống/ngôn ngữ khác |

### Prompt-only vs. constrained output

**Prompt-only** ("Hãy trả JSON đúng schema này"): model vẫn có thể thêm prose, bọc code fence, trả enum ngoài danh sách, thiếu field, hoặc trả field sai kiểu.

**Constrained output:**
- Một số LLM API hỗ trợ structured output có ràng buộc bằng schema.
- Cơ chế này mạnh hơn việc chỉ viết "chỉ trả JSON" trong prompt.
- Tập JSON Schema được hỗ trợ có thể khác nhau giữa nhà cung cấp và model.

**Validation** phát hiện: thiếu field, sai type, sai enum, dữ liệu không tuân theo schema.

> Schema kiểm tra **cấu trúc**. Schema **không** kiểm tra tính đúng đắn của **nội dung**. Severity vẫn có thể sai nếu issue thực tế chỉ là lỗi nhỏ.

---

## 4. Function Calling và Tool Use

**Structured output** trả dữ liệu:
```json
{"severity": "P0", "component": "payment"}
```

**Function calling** cho model đề xuất một hành động có cấu trúc:
```json
{"name": "get_component_owner", "arguments": {"component": "payment"}}
```

### Tool schema

Một tool tối thiểu cần: `name`, `description`, schema của `arguments`.

```python
from langchain.tools import tool

@tool
def get_component_owner(component: str) -> str:
    """Trả về team chịu trách nhiệm cho component."""
    ...
```

### Tool call và thực thi

Model **không thể**:
- chạy Python;
- truy cập database;
- gọi REST API;
- có thêm permission chỉ vì nó sinh ra tool call.

Model chỉ sinh một object mô tả hành động mà **application** có thể thực hiện. Application thực thi và quyết định có chạy hay không.

**Tool result** phải được gắn với tool call tương ứng. Model dùng kết quả đó để tạo response tiếp theo.

### Demo: triage và chọn team

- Input: "Nút thanh toán trả HTTP 500 với mọi thẻ Visa từ 14:30. Hãy triage issue và cho biết team nào cần xử lý."
- Model đề xuất: `get_component_owner("payment")`.
- Application thực thi: `get_component_owner("payment")` → kết quả `{"component": "payment", "owner": "checkout-platform"}`.
- Model nhận result rồi mới tạo final response hoặc structured triage tiếp theo.

### Tool validation

Giả sử model tạo `{"name": "get_component_owner", "arguments": {"component": "payment-api-v2"}}`:
- `component` đúng kiểu string;
- nhưng hệ thống có thể **không tồn tại** component `payment-api-v2`.

> **Đúng kiểu không đồng nghĩa đúng ý nghĩa.**

### Structured output và tool call

| | Structured output | Tool call |
|---|---|---|
| Model làm gì | Trả dữ liệu cho ứng dụng | Đề xuất hành động cho ứng dụng |
| Ràng buộc | Output tuân theo schema | Arguments tuân theo tool schema |
| Ứng dụng làm gì | Đọc dữ liệu | Quyết định có thực thi hay không |

---

## 5. Cầu nối sang AI agent

**Issue Triage App** giờ có thể phân tích dữ liệu và đề xuất hành động. Mỗi bước đều có interface mà ứng dụng có thể kiểm tra.

**Nhưng đây chưa phải agent.** Một function call chỉ là một lần model yêu cầu một hành động có cấu trúc. LLM-powered app hiện tại vẫn có luồng xử lý do code định trước.

Xây dựng AI agent cần thêm:
- **vòng lặp nhiều bước** (agent loop);
- **điều kiện dừng**.

**Agent loop** tổ chức nhiều lần quan sát và hành động thành một task nhiều bước. Buổi sau sẽ đi sâu: goal, observation, chu trình reasoning/action, ReAct, planning, termination condition và failure modes.

---

## 6. Tổng kết

- LLM-powered app bắt đầu từ một model call có cấu trúc.
- Token và context window xác định model nhận được bao nhiêu thông tin và chi phí của mỗi call.
- Prompt giúp mô tả task; context engineering quyết định thông tin nào được đưa vào model.
- Structured output biến output thành dữ liệu mà code có thể xử lý.
- Function calling biến yêu cầu hành động của model thành một tool call mà application kiểm soát.
- Các cơ chế này là nền tảng để tiếp tục xây dựng AI agent bằng agent loop ở buổi sau.
