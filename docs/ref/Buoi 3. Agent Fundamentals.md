# Buổi 03 – Agent Fundamentals

*Kỹ thuật xây dựng hệ thống Agentic AI · SE373*

**Mục tiêu buổi học:** dựng được vòng lặp agent có điều kiện dừng kiểm chứng được, và đọc trace để chỉ ra chỗ hỏng.

## Nội dung

1. Vòng lặp agent
2. ReAct và các mẫu suy luận
3. Điều kiện dừng
4. Agent debugging

---

## Phần 01 – Vòng lặp agent

### Định nghĩa Agent

> **Agent:** phần mềm có khả năng tự chủ hoạt động, đưa ra quyết định để đạt mục tiêu mà không cần con người can thiệp liên tục.

- **Tự chủ:** tự quản lý và quyết định bước đi tiếp theo.
- **Chủ động:** tự lên kế hoạch và khởi xướng hành động.
- **Phản ứng:** nhận thức môi trường và thích ứng kịp thời.

**Agent = model quyết định lúc chạy.** Model chọn bước, dùng tool, nhận output, lặp lại.

Ví dụ: "Tìm vé máy bay → chuyến đầu hết chỗ → agent xem kết quả và chọn tìm chuyến khác."

### Cấu tạo tối thiểu

```
agent = goal + tools + loop + termination
```

1. **Goal:** mục tiêu cần đạt.
2. **Tools:** các công cụ thêm cho agent.
3. **Loop:** đưa kết quả hành động trở lại làm đầu vào.
4. **Termination:** cơ chế quyết định dừng hay chạy tiếp.

> Thiếu termination là tốn kém nhất.

**Goal** mô tả trạng thái cần đạt, không phải danh sách bước cần làm.

| Không phải goal | Là goal |
|---|---|
| Tóm tắt đoạn văn này | Tìm commit làm hỏng `test_checkout` và mở issue |

Một lệnh, một bước không cần vòng lặp.

### Tools và Loop

- **Tools:** hàm bên ngoài mà model gọi được qua giao thức tool calling; có tên, mô tả và schema tham số.
- **Loop:** chu trình đưa kết quả của hành động vừa thực hiện trở lại làm đầu vào cho lần suy luận kế tiếp.

- Không có tool thì model chỉ sinh văn bản.
- Một lần gọi tool chưa phải agent.

Chu trình: **Gọi tool → Sinh thêm dữ liệu → Quan sát/Đánh giá → Lặp hoặc Dừng.**

### Termination

Cơ chế quyết định chạy tiếp hay dừng lại. Gồm điều kiện hoàn thành và các giới hạn cứng. Thiếu nó, agent không có điểm kết thúc và chi phí không có trần.

### Agent truyền thống và AI agent

Câu hỏi phân loại: **bước tiếp theo do ai quyết định?**

- **Chain:** lập trình viên quyết định trước mọi bước.
- **Workflow / Router:** model chọn nhánh trong tập có sẵn do lập trình viên định nghĩa.
- **AI Agent:** model quyết định lúc chạy (goal → model chọn bước → tool → output).

### Sơ đồ trục: vòng lặp AI Agent

| Bước | Ai thực hiện | Việc làm |
|---|---|---|
| 01 | Harness | Dựng ngữ cảnh |
| 02 | **Model** | Đề xuất tool |
| 03 | Harness | Gọi tool |
| 04 | Harness | Ghi kết quả |
| 05 | Harness | Xét điều kiện dừng |

- Nếu chưa xong: nạp observation mới rồi lặp tiếp.
- Ở bước "Xét điều kiện dừng" có 3 hành động: **lặp tiếp, chờ người, hoặc thoát**.
- Chỉ bước 02 là của model. Bốn bước còn lại là code do bạn viết.

### Ranh giới model và harness

```
HARNESS (code của bạn): Dựng context
  → MODEL: Đọc context → Sinh tool_calls
  → HARNESS (code của bạn): Parse và validate → Thực thi → Ghi kết quả → Xét dừng
  → observation → (lặp)
```

### Tool call là dữ liệu

```json
{ "name": "weather_forecast", "args": {"town": "Quy Nhơn"}, "id": "call_w1" }
```

Dùng `id` để ghép kết quả vào lịch sử hội thoại:

```
AIMessage   tool_calls=[{name: weather_forecast, args: {town: "Quy Nhơn"}, id: call_w1}]
ToolMessage tool_call_id=call_w1 content={"weather": "nắng"}
```

### Observation: chuẩn hoá structured output

| Observation kém | Observation tốt |
|---|---|
| Trang HTML thô: `<div id="mw-content"><p>Nha Trang, thuộc Khánh Hoà, nổi tiếng với bãi biển dài…` | `{"town": "Nha Trang", "weather": "nắng", "temperature": 31}` |

Output của LLM nên ở dạng structured output theo JSON.

### Chi phí của lịch sử

- Mỗi vòng nạp lại toàn bộ lịch sử, mà lịch sử dài thêm sau mỗi vòng.
- Tổng chi phí tăng theo **bình phương** số vòng: gấp đôi số vòng thì chi phí gấp khoảng bốn lần.

Số giả định để tạo trực giác: 3.000 token nền, mỗi vòng thêm 500 token lịch sử. Token tích luỹ qua các vòng 1–8 tăng dần: 3 → 6,5 → 10,5 → 15 → 20 → 25,5 → 31,5 → 38 (đơn vị: nghìn token, theo slide).

### Giới hạn cứng (ngân sách vòng lặp)

1. **Bước:** tối đa bao nhiêu vòng.
2. **Token:** tối đa bao nhiêu token cho cả phiên.
3. **Thời gian:** tối đa bao nhiêu giây.
4. **Chi phí:** trần chi phí cho một tác vụ.

### Tổng kết phần 1

1. Agent là model chọn bước tiếp theo lúc chạy, trong giới hạn của harness.
2. `agent = goal + tools + loop + termination`.
3. Model sinh lời gọi tool; harness thực thi, ghi state và xét điều kiện dừng.
4. Thiết kế cách observation (output, điều kiện dừng…).

---

## Phần 02 – ReAct và các mẫu suy luận

Cách tổ chức suy luận bên trong vòng lặp.

### ReAct

ReAct (Reasoning + Acting, Yao và cộng sự, 2022) là kiến trúc cốt lõi giúp AI agent liên tục suy luận, hành động và quan sát thực tế. ReAct **không phải** một thư viện, cũng không phải một model.

**Chu trình:** Suy luận → Hành động → Quan sát → (quan sát quay lại làm đầu vào cho suy luận tiếp theo).

### Ba cách tổ chức suy luận

- **Chain of thought:** suy luận nhiều bước nhưng không dùng môi trường ngoài.
- **Action only:** hành động nhưng không có bước suy luận tường minh.
- **ReAct:** suy luận, hành động, quan sát, rồi suy luận tiếp.

### Vì sao ReAct hiệu quả hơn

- Dữ kiện từ môi trường đi vào giữa chuỗi suy luận, thay vì chỉ dựa vào trí nhớ của model.
- Hướng đi được điều chỉnh sau mỗi quan sát, không cố định từ đầu.
- Trace ghi lại từng vòng, nên chẩn đoán được khi sai.

### Ví dụ: vòng lặp đặt vé máy bay

Mục tiêu: "đặt giúp tôi một vé bay".

Ở vòng 3, agent lặp tiếp:
- **Bước 1 – Quyết định:** chọn hành động tiếp theo.
- **Bước 2 – Hành động:** `book_seat(thu_3)`.
- **Bước 3 – Quan sát:** đã xác nhận. Xong chưa? Rồi.

Ngữ cảnh đã có 12 chuyến phù hợp, trống thứ ba → thứ năm đã xác nhận mã 4XJ2. Kích thước ngữ cảnh: 4.100 token.

> Agent không trả lời trong một lượt: nó quay vòng cho tới khi xong, và mỗi vòng gửi lại toàn bộ lịch sử.

### Plan-then-execute

Gọi model **một lần** để sinh trọn kế hoạch, rồi thực thi từng bước theo kế hoạch đó.

Luồng: Goal → Model sinh kế hoạch → Người duyệt (đồng ý / từ chối) → Bước 1 → Bước 2 → Bước 3 → Kết quả.

- **Ưu điểm:** giữ vững định hướng khi xử lý tác vụ dài; tiết kiệm chi phí và hỗ trợ chạy song song; dễ dùng mô hình nhỏ để thực thi; kế hoạch nhìn thấy được trước khi chạy nên duyệt được và ước lượng được chi phí.
- **Nhược điểm:** thiếu linh hoạt khi tình huống thay đổi bất ngờ; lỗi ở bước đầu làm hỏng toàn bộ phần sau; tốn thời gian ban đầu để lập kế hoạch.

> Đây là đánh đổi giữa khả năng duyệt trước và khả năng thích nghi.

### Mẫu lai "ReAct + Plan"

Lập kế hoạch → thực thi k bước → nếu observation đổi đáng kể thì lập lại kế hoạch, nếu không thì tiếp tục → xong.

LangChain 1.x hỗ trợ mẫu này qua `TodoListMiddleware`.

### Reflection (tự phản tỉnh)

Mẫu kiến trúc cho phép AI agent tự đánh giá và sửa lỗi kết quả của chính mình.

Luồng: Yêu cầu → LLM sinh bản nháp → LLM soi và chấm nháp theo tiêu chí (chính xác, logic, văn phong) → chưa đạt thì góp ý và sửa lại → đạt thì trả kết quả cuối.

Tự động phát hiện và sửa lỗi sai, nâng cao đáng kể chất lượng đầu ra.

### Bảng chọn mẫu

| Mẫu | Chọn khi | Rủi ro chính |
|---|---|---|
| ReAct | Không đoán được số bước | Lặp vô hạn, trôi mục tiêu |
| Plan-then-execute | Cần duyệt trước | Kế hoạch lỗi thời |
| Lai (ReAct + Plan) | Tác vụ dài, môi trường biến động | Khó debug hơn |
| Reflection | Có tín hiệu kiểm chứng ngoài | Nhân đôi chi phí |

### Ví dụ: `create_agent` trong LangChain

LangChain và LangGraph 1.0 phát hành 22/10/2025. API chuẩn hiện nay là `create_agent` trong `langchain.agents`.

```python
agent = create_agent(
    model=os.environ["SE373_MODEL"],
    tools=TOOLS,
    system_prompt="Chỉ dùng tool để lấy thông tin, kể cả tên điểm đến.",
    middleware=[ModelCallLimitMiddleware(run_limit=8, exit_behavior="end")],
)
result = agent.invoke({"messages": [{"role": "user", "content": CAU_HOI}]})
```

**So sánh:**
- **Không có system prompt:** agent gọi thẳng `weather_forecast("Nha Trang")`, `weather_forecast("Đà Nẵng")`. Tên điểm đến lấy từ trí nhớ của model.
- **Có system prompt:** agent gọi `search_travel_info(...)` trước, rồi `weather_forecast` với tên lấy từ kết quả tìm kiếm.

> Có tool không có nghĩa là agent sẽ dùng tool.

### Tổng kết phần 2

1. **ReAct:** Suy luận → Hành động → Quan sát kết quả → Suy luận tiếp.
2. **Plan-then-execute:** lập bản kế hoạch tổng thể gồm nhiều bước → thực thi từng bước.
3. **Reflection:** tự tạo ra kết quả → tự đánh giá tìm lỗi → sửa lại.
4. Có tool chưa chắc agent dùng tool.

---

## Phần 03 – Điều kiện dừng

### Định nghĩa

> **Termination condition:** tiêu chí để agent kết thúc vòng lặp thực thi khi đạt mục tiêu hoặc chạm giới hạn.

Mặc định của framework: **dừng khi model thôi gọi tool.**

### Năm điều kiện dừng

Sau mỗi vòng, harness kiểm tra:

| # | Điều kiện | Ví dụ | Loại |
|---|---|---|---|
| 1 | **Đạt mục tiêu** | Vé đã confirmed | Bình thường |
| 2 | **Hết ngân sách** | Dò 12 chuyến, đều trên 2 triệu | Bất thường |
| 3 | **Phát hiện lặp** | `check_seat` lỗi ba lần liền | Bất thường |
| 4 | **Bế tắc** | Đổi hướng liên tục, vẫn chỉ đạt 1/2 ràng buộc | Bất thường |
| 5 | **Cần con người** | Vé không hoàn, vượt hạn mức | Bình thường |

**Kết quả tương ứng:** đạt mục tiêu → trả kết quả; hết ngân sách, lặp, bế tắc → log và báo người; cần con người → chờ phê duyệt.

**Checklist harness chạy sau mỗi vòng:**

| # | Chạy khi nào | Kiểm gì | Kết thúc kiểu |
|---|---|---|---|
| 0 | Trước khi thực thi tool | Quyền hạn của hành động sắp làm | Cần con người |
| 1 | Sau khi có observation | Tiêu chí hoàn thành | Đạt mục tiêu (bình thường) |
| 2 | Sau khi có observation | (tool, args) có trùng vòng trước | Phát hiện lặp (bất thường) |
| 3 | Sau khi có observation | Đại lượng tiến triển có nhúc nhích | Bế tắc (bất thường) |
| 4 | Sau khi có observation | Vòng, token, thời gian, tiền | Hết ngân sách (bất thường) |

> Ngân sách kiểm cuối cùng: đặt nó lên đầu thì mọi lỗi đều báo về là "hết ngân sách", và bạn mất chẩn đoán.

### Các cách cài đặt điều kiện dừng

- **Sensor computational:** test, linter, type checker. Xác định, chạy trong mili giây, không tốn token.
- **Sensor inferential:** một model chấm output của model. Không xác định, tốn thêm chi phí. Dùng khi không có cách đo máy móc.

> Ưu tiên sensor computational bất cứ khi nào có thể. (Nguồn: khung guides và sensors của Böckeler, martinfowler.com, 04/2026.)

### 5 điều kiện dừng: minh hoạ với bài toán đặt vé

**1. Đạt mục tiêu.** Model thôi gọi tool, nghĩa là nó tự cho rằng đã xong.
- V1 `search_flights("SGN", "DAD", "07/10")` → 12 chuyến
- V2 `check_seat("VN122")` → 3 ghế
- V3 `book_seat("VN122", "12A")`
- V4 `pay("4XJ2", "corp_card")`
- V5 `get_booking("4XJ2")` → 4XJ2 · held → paid → confirmed · 1.850.000

Đây là kiểu dừng duy nhất ta mong muốn. Phải kiểm chứng kết quả trước khi tin. Cũng là kiểu nguy hiểm nhất khi sai, vì nó trông giống thành công.

**2. Hết ngân sách.** Harness đếm và thấy đã chạm trần bước, token, thời gian hoặc tiền.
- Mỗi vòng `check_seat` một chuyến khác (VN122 → VJ604 → QH118 → …), không lặp, vẫn có tiến triển, nhưng chạm trần 12 vòng.
- Xác định, không phụ thuộc model. LangGraph: `GraphRecursionError`. LangChain: `ModelCallLimitMiddleware`.
- Dừng bất thường: phải log và trả kết quả dở dang cho người.

**3. Phát hiện lặp.** Agent gọi lại cùng một hành động hoặc nhận lại cùng một kết quả mà không tiến gần hơn tới mục tiêu.
- V2, V3, V4 đều là `check_seat("VN122")` → `{"error": "timeout"}`.
- (tool, args) trùng ba lần, ngân sách vẫn còn 8 vòng.
- Framework không có sẵn cơ chế này; đây là code bạn phải tự viết.
- So sánh theo (tool, args), không so observation. Gọi lại `get_booking` để chờ confirmed là polling hợp lệ.

**4. Bế tắc.** Agent không lặp nhưng cũng không tiến: mỗi vòng thử một tool khác và đều thất bại.
- V4 `search_flights` sai giờ; V5 sai ngày; V6 `check_seat("VJ612")` hãng khác, sai giá; V7 `search_flights("SGN", "HUI")` bay Huế, sai điểm đến.
- Ràng buộc đã thoả: 1/2, đứng yên suốt 6 vòng.
- Khó thấy hơn lặp, vì trace nhìn rất bận rộn. Phát hiện bằng cách đo một đại lượng tiến triển của bài toán.

**5. Cần thông tin / approval.** Agent chạm tới một hành động vượt thẩm quyền và dừng lại chờ phê duyệt.
- V3: model định gọi `book_seat("VN122", "12A")`, giá 1.950.000đ, vé không hoàn.
- Vì sao hỏi: vượt hạn mức 1.500.000đ và không hoàn được.
- Ví dụ các hành động cần duyệt: xoá dữ liệu, chuyển tiền, gửi mail cho khách, merge vào main.
- Kiểm quyền chạy **trước** khi thực thi; bốn điều kiện kia chạy **sau** khi có observation.

### Phân loại dừng

| | Đạt mục tiêu | Hết ngân sách | Phát hiện lặp | Bế tắc | Cần con người |
|---|---|---|---|---|---|
| Ai phát hiện | Model | Harness đếm | Harness so sánh | Harness đo tiến triển | Harness kiểm quyền |
| Bình thường? | Có | Không | Không | Không | Có |

> Dừng bất thường mà im lặng thì biến một lỗi thấy được thành một lỗi ẩn.

### Tiêu chí hoàn thành (completion criteria)

> Tiêu chí hoàn thành là các quy tắc lập trình khách quan, được hệ thống bên ngoài kiểm chứng để xác nhận tác vụ đã xong, hoàn toàn độc lập với phán đoán của model.

Ví dụ với bài đặt vé:

```python
get_booking(code).status == "confirmed" and paid == True
and price <= 2_000_000 and depart_date == "2026-10-07" and depart_time < "12:00"
```

Phân biệt cách đánh giá "đã xong":
- ❌ **Chủ quan:** phụ thuộc vào model tự tuyên bố ("model cảm thấy đã thu thập đủ thông tin" thì dừng).
- ✅ **Khách quan:** dùng code kiểm tra chính xác trạng thái.

**Bốn dạng tiêu chí kiểm chứng được:**

1. **Vị từ chạy bằng code:** pytest exit code 0, HTTP 200, `get_booking(c).status == "confirmed"`.
2. **Schema hợp lệ:** output parse được theo Pydantic; kết quả `book_seat` parse được theo model `Booking`.
3. **Kiểm chứng chéo:** agent báo đã tạo issue thì gọi API đọc lại; giá trong `get_booking` khớp giá đã thấy ở `check_seat`.
4. **Người duyệt:** khi ba cách trên không áp dụng được. Ví dụ: vé không hoàn phải có duyệt trước khi pay.

Dạng 1 là sensor computational: xác định, chạy trong mili giây, không tốn token.

### Ba tín hiệu phát hiện lặp

- **Trùng action:** cùng (tool, args) xuất hiện lại trong cửa sổ vài vòng.
- **Trùng observation:** tham số khác nhau nhưng kết quả giống hệt.
- **Không tiến triển:** một đại lượng của bài toán đứng yên qua N vòng.

Tín hiệu thứ ba bắt được kiểu lặp mà hai tín hiệu đầu bỏ sót: agent đổi tool mỗi vòng nhưng vẫn đứng yên.

**Code tham khảo: bộ phát hiện lặp**

```python
class LoopDetector:

    def __init__(self, window=6, repeat_k=2, stall_n=5):
        self.recent = deque(maxlen=window)   # chỉ so cửa sổ gần
        self.k, self.n, self.last, self.stall = repeat_k, stall_n, None, 0

    def check(self, tool, args, progress):
        fp = (tool, repr(sorted(args.items())))
        if self.recent.count(fp) + 1 >= self.k:
            return "LOOP"
        self.recent.append(fp)
        self.stall = self.stall + 1 if progress == self.last else 0
        self.last = progress
        return "STALL" if self.stall >= self.n else None
```

- Tham số `progress` do bạn truyền vào, là đại lượng của bài toán, ví dụ số test còn fail.
- Không có bộ phát hiện lặp tổng quát.

### Bàn giao cho con người (handoff)

- **Trạng thái:** đã làm tới đâu, hành động nào đã có tác dụng phụ.
- **Những gì đã thử:** hướng nào đã hỏng và vì sao.
- **Câu hỏi cụ thể:** ví dụ "Dùng bảng `orders` hay `orders_v2`?"

> Bàn giao tốt là bàn giao mà người nhận trả lời được trong 30 giây.

Đây là lớp harness **handoff**, lớp thứ 12.

### Tổng kết phần 3

1. Năm điều kiện dừng (termination condition).
2. Tiêu chí hoàn thành phải kiểm chứng được từ logic code.
3. Phát hiện lặp là code bạn tự viết; framework không làm hộ.

---

## Phần 04 – Agent Debugging

### Quy trình 4 bước

1. **Tái hiện:** chạy lại với đúng đầu vào cũ; lưu toàn bộ nhật ký (log) từng bước.
2. **Khoanh vùng:** tìm vòng lặp sai **đầu tiên**. Tuyệt đối không nhìn kết quả cuối.
3. **Xác định loại lỗi:** đối chiếu 4 dấu hiệu đặc trưng, phân loại chính xác kiểu lỗi.
4. **Đặt kiểm tra:** thêm code chặn tại vòng bị lỗi, chạy lại để xác nhận giả thuyết.

Kiểu lỗi lặp lại được của agent thường gọi là **failure mode**.

### Bảng tra các failure mode

| Dấu hiệu trong log | Tên loại lỗi | Đặt harness |
|---|---|---|
| Gọi một công cụ lặp lại, kết quả y hệt | Lặp không tiến bộ | Đếm số lần gọi công cụ vô ích |
| Xuất hiện số liệu, ngày, ID không có trong dữ liệu thật | Bịa đặt thông tin (hallucination) | Đối chiếu lại kết quả trước khi gửi |
| Hành động cuối bị lạc đề so với yêu cầu gốc | Quên yêu cầu | Kiểm tra lại ràng buộc trước khi chốt |
| Log trơn tru, không lặp nhưng sai từ kết luận đầu | Tin dữ liệu sai | Ép công cụ trả về trạng thái rõ ràng |

### Vấn đề 1: Lặp lại nhưng không tiến bộ

Agent thử cách khác nhưng nhận lại cùng một kết quả, nên không có thông tin mới để đi tiếp.

- **Dấu hiệu:** gọi một công cụ lặp lại, kết quả y hệt. Công cụ không trả về mã lỗi chi tiết.
- **Vì sao:** không có thông tin mới để đi tiếp.
- **Code chặn:** đếm số lần gọi không tiến triển để ngắt luồng hoặc báo người dùng.

**Tình huống:** hỏi thời tiết Vũng Tàu, agent đổi cách viết tên rồi gọi lại:
- V1 `weather_forecast(town="Vung Tau")` → `{"error": "not found"}`
- V2 `weather_forecast(town="Vũng Tàu")` → `{"error": "not found"}`
- V3 `weather_forecast(town="Vung Tau City")` → `{"error": "not found"}`
- V4 `weather_forecast(town="Vung Tau")` → `{"error": "not found"}`
- V5 đến V35: luân phiên năm cách viết tên, kết quả y hệt.
- V36: hết giới hạn 36 lượt, dừng, không có câu trả lời.

Câu hỏi: từ vòng nào đã đủ bằng chứng rằng agent đang lặp? (Gợi ý: V4 gọi lại đúng cách viết đã lỗi ở V1.)

**Cách xử lý:** thay `"not found"` bằng lỗi nói được đường đi khác:

```json
{"status": "invalid_town", "hint": "Gọi list_supported_towns để lấy danh sách hợp lệ", "supported_count": 63}
```

### Vấn đề 2: Bịa đặt thông tin (hallucination)

Agent tự chế ra dữ liệu để trả lời. Lỗi ngầm: chương trình vẫn chạy trơn tru, không báo lỗi.

**Tình huống:** người dùng hỏi về đơn hàng ORD-88123.
- V1: `get_order(order_id="ORD-88123")` → `{"status": "in_transit", "carrier": "GHN", "customer_id": "CUS-4471"}`
- V2: `get_tracking(order_id="ORD-88123")` → `{"last_scan": "Kho trung chuyển Bình Dương", "scanned_at": "06/09 18:40"}`
- V3 (agent trả lời): "Đơn đang trên đường giao, quét gần nhất tại Bình Dương lúc 18:40. **Tổng tiền 1.250.000đ**, đã gồm 30.000đ phí vận chuyển, thẻ VISA đuôi 4412."

**Đối chiếu từng khẳng định với tool:**
- "1.250.000đ" → không có nguồn ✗
- "30.000đ" → không có nguồn ✗
- "VISA 4412" → không có nguồn ✗
- "GHN" → call_b1 ✓
- "18:40 06/09" → call_b2 ✓

**Cách xử lý, ba cách chặn:**
- Chỉ cho phép gọi các tên trong danh sách (ví dụ agent gọi `get_order_price` không tồn tại).
- Kiểm tra (validate) tham số trước khi gọi hàm (ví dụ `order_id=123` khi cần chuỗi).
- Đối chiếu câu trả lời với kết quả thật từ tool: lỗi tự chế dữ liệu là nguy hiểm nhất, và chỉ bắt được khi phân tích câu trả lời.

Hai lỗi đầu có thể bắt ngay ở tầng code; lỗi thứ ba bắt buộc phải phân tích câu trả lời.

### Vấn đề 3: Quên yêu cầu ban đầu

Agent vẫn đang làm gì đó, nhưng kết quả không còn đáp ứng yêu cầu ban đầu.

- **Dấu hiệu:** việc ở vòng cuối không còn liên quan tới yêu cầu lúc đầu; yêu cầu lùi xa dần khi nhật ký dài ra.
- **Code chặn:** giữ yêu cầu ở chỗ rõ ràng; trước khi trả lời, kiểm lại đúng ngày, đúng giờ, trong ngân sách.

**Tình huống:** người dùng yêu cầu "Tìm vé TP.HCM → Đà Nẵng sáng thứ Năm, dưới 2 triệu."
- `search_flights("SGN", "DAD", "24/09")` → 12 chuyến
- `check_seat("VN122")` → 2.310.000 · quá giá
- `get_airline_reviews("VN")` → 4,2/5; `get_airline_reviews("VJ")` → 3,8/5
- `search_flights("SGN", "DAD", "25/09")` → chiều thứ Sáu
- Đề xuất: "chuyến chiều thứ Sáu, 2.400.000đ, hãng đánh giá tốt hơn."

Không vòng nào báo lỗi. Agent đã rời khỏi yêu cầu ban đầu từ vòng nào?

**Cách xử lý:** ghi yêu cầu và ràng buộc thành dữ liệu, rồi kiểm lại ngay trước khi trả lời:

```python
yeu_cau = {"ngay": "07/10", "buoi": "sang", "tran_gia": 2_000_000}
check(ve, yeu_cau)  # trước khi trả lời
```

### Vấn đề 4: Tin vào dữ liệu sai

Công cụ trả kết quả mơ hồ → agent tự diễn dịch sai → mọi bước sau, dù hợp lý, đều đã sai ngay từ đầu.

- **Đặc điểm:** một kết quả từ công cụ bị sai ở bước đầu, kéo theo toàn bộ suy luận phía sau nhất quán với cái sai đó.
- **Vì sao khó:** log "sạch" (không lặp, không báo lỗi, dừng đúng cách) nên cực kỳ khó phát hiện.
- **Code chặn:** ràng buộc tool trả trạng thái rõ: có dữ liệu · không có dữ liệu · gọi sai · công cụ lỗi.

**Tình huống:** service `payment` trả lỗi 500 từ 14:00.
- `search_logs(service="payment", level="ERROR")` → `''`
- `list_deploys(service="payment")` → dp-5512, 13:47, commit 9f2a1c7
- `get_commit(sha="9f2a1c7")` → "refactor: đổi tên biến", +12 −12
- `search_logs(service="payment", level="ERROR")` → `''` (lần hai)
- Kết luận của agent: "Không có log ERROR nào sau 13:47 nên lỗi không đến từ ứng dụng. Commit chỉ đổi tên biến nên an toàn. Chuyển SRE, không cần rollback."

Câu hỏi: agent đã biến `''` thành khẳng định nào mà nó chưa kiểm chứng? (Gợi ý: `''` có thể nghĩa là tham số `level` sai, không phải "không có log".)

**Cách xử lý:** tool phải trả kết quả rõ ràng. Nếu tool chỉ trả về một chuỗi rỗng, agent không đủ dữ kiện để biết nên làm gì tiếp:

```json
{"status": "ok", "matched": 0, "logs": []}
{"status": "invalid_param", "param": "level", "allowed": ["error", "warn", "info"]}
```

Định dạng lại kết quả (ví dụ dùng JSON) để định hướng hành động cho agent.

### Tổng kết phần 4

1. **Tái hiện rồi khoanh vùng:** bắt đúng vòng sai đầu tiên, bỏ qua kết quả cuối.
2. **Phân loại lỗi:** xác định chính xác 1 trong 4 kiểu lỗi.
3. **Cảnh giác lỗi ngầm:** hai lỗi cuối không tự báo động (log sạch nhưng vẫn sai).
4. **Đặt kiểm tra:** thêm code chặn ngay tại vòng lỗi đó và chạy lại.

---

## Tổng kết buổi

- Agent chọn bước tiếp theo lúc chạy, trong giới hạn của harness.
- Vòng lặp có năm chặng (dựng ngữ cảnh → model đề xuất tool → harness gọi tool → ghi kết quả → xét điều kiện dừng).
- Ba mẫu suy luận: ReAct, Plan-and-Execute, Reflection.
- Năm kiểu dừng trong agent loop.
- Agent debugging với bốn failure mode.

Buổi 4 là harness engineering: khung guides và sensors, và giải phẫu một agent harness đầy đủ.
