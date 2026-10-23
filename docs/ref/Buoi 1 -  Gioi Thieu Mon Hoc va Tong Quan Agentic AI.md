# Buổi 01 – Tổng quan LLM và Agentic AI

*Kỹ thuật xây dựng hệ thống Agentic AI · SE373 · Khoa Công nghệ Phần mềm, UIT*

**Mục tiêu buổi học:** phân loại được các hệ thống AI với LLM, giới thiệu 12 lớp harness.

---

## Phần 01 – Giới thiệu khái niệm

### LLM là gì?

Không phải ba thứ song song, mà là ba lớp bao nhau:

- **Trí tuệ nhân tạo (AI):** máy làm việc trước đây cần trí óc con người. Có từ những năm 1950 (Gmail lọc thư rác, TikTok gợi ý video, Face ID). Chủ yếu **phân loại** và **dự đoán**.
- **AI tạo sinh (Generative AI):** bùng nổ từ 2022. Không chỉ nói "đây là ảnh con mèo" mà **vẽ ra** một con mèo chưa từng tồn tại. Tạo chữ, ảnh, tiếng, code.
- **LLM (Large Language Model – mô hình ngôn ngữ lớn):** AI tạo sinh chuyên về chữ. ChatGPT, Claude, Gemini, Copilot, DeepSeek đều thuộc nhóm này. Đây là trọng tâm của cả học phần.

### Cơ chế lõi: trò chơi "đoán từ tiếp theo"

LLM đoán một từ, gắn từ đó vào cuối câu, rồi lại đoán từ tiếp theo dựa trên tất cả những gì đã có.

> "Thủ đô của Việt Nam là ___"
> → Hà Nội (92%), Hà Nội cũ (3%), thành phố Huế (2%), … (1%)

> "Sáng nay trời mưa nên tôi mang theo cây…" → "dù"

Người đọc nghĩ ra chữ "dù" không phải vì tra cứu được đáp án đúng, mà vì trong hàng nghìn câu tiếng Việt đã nghe, sau bối cảnh đó chữ "dù" xuất hiện nhiều nhất. LLM làm đúng như vậy, chỉ khác là nó đã "học" hàng nghìn tỉ chữ.

### Agentic Application là gì?

Ví dụ sản phẩm triển khai: **Exec.com** – nền tảng AI roleplay và coaching cho nhân sự, có phân tích và phản hồi, đo kỹ năng theo thời gian. Được các tập đoàn Mỹ dùng cho đào tạo lãnh đạo và đội bán hàng.

Các ứng dụng Agentic production có chung công thức **model + harness**:

| Ứng dụng | Mô tả |
|---|---|
| Customer Support Agent | Trực kênh khách hàng đa nền tảng; trả lời theo tri thức riêng của doanh nghiệp, tạo và chuyển ticket cho người thật khi vượt phạm vi |
| Interview Agent | Tự động hoá vòng phỏng vấn sơ loại: chấm điểm nhất quán, rút ngắn 70% thời gian vòng đầu, dashboard cho nhà tuyển dụng |
| Audit Support Agent | Hỗ trợ nghiệp vụ kiểm toán nhà nước với mô hình local LLM |
| Agent-2-Agent | Phân tích mô hình vận hành doanh nghiệp, đề xuất điểm nghẽn và khởi tạo nhanh agent vận hành |
| Fintech Agent | Xử lý hồ sơ, nhập liệu và tác vụ lặp lại trong tư vấn tài chính (mortgage broker, Úc) |
| Content Writer Agent | Viết nội dung tối ưu cho câu trả lời của AI (AEO), theo dõi cách các model trích dẫn thương hiệu |

### Định vị môn học

- **Không** yêu cầu kiến thức machine learning.
- **Không** phải môn học cách viết prompt, môn giới thiệu LangChain/LangGraph, hay dạy dùng ChatGPT.
- **Là** môn kỹ thuật hệ thống, có một thành phần cốt lõi không tất định. Model được xem như một dịch vụ bên ngoài, không huấn luyện model.

---

## Phần 02 – Phân biệt Chatbot, RAG, Workflow và Agent

### Bốn nấc ứng dụng

Ba năm tiến hoá: **completion → chat → tool use → agent**. Mỗi nấc làm được thêm một việc mới và trao thêm quyền quyết định cho model.

| Nấc | Đặc điểm | Ai quyết định bước sau? |
|---|---|---|
| Completion | Vào chuỗi, ra chuỗi. Model là một hàm thuần | Code |
| Chat | Thêm vai trò system/user/assistant, giữ lịch sử nhiều lượt | Code |
| Tool use | Model sinh cấu trúc mô tả một lời gọi hàm. Code gọi, model chỉ đề nghị | Code |
| Agent | Đặt tool use vào vòng lặp; model tự quyết định bước tiếp | **Model** |

Xu hướng duy nhất: quyền quyết định chuyển dần từ code sang model, đánh đổi tính dự đoán để lấy sự linh hoạt.

### Chatbot và RAG app

**Chatbot**
- Tập trung vào hội thoại, duy trì ngữ cảnh nhiều lượt, không tự hành động.
- Phản hồi dựa hoàn toàn vào kiến thức đã huấn luyện của model.
- Dễ nói sai một cách tự tin (ảo tưởng).

**RAG app**
- Hỏi–đáp buộc câu trả lời bám nguồn vào kho tri thức nội bộ.
- Hoạt động qua hai pha: nạp tài liệu ngoại tuyến (ingest) và tìm kiếm/truy hồi ngữ cảnh trực tuyến.
- Không tìm thấy thông tin thì không trả lời, hoặc trích dẫn không khớp nội dung nguồn.

> Agent **có thể dùng** RAG như một tool; một RAG app **không phải** agent.

**Kiến trúc chatbot nhiều lượt:** Lượt 1 "Summarize: War and Peace.pdf" → LLM sinh 1.000 từ. Lượt 2 "Give me only 2–3 sentences" → 50 từ. Lượt 2 khả thi nhờ lịch sử hội thoại còn trong cửa sổ ngữ cảnh. Đây là *state*, và state có giới hạn phụ thuộc model. Khi hội thoại vượt dung lượng context, hệ thống phải cắt hoặc nén.

### Workflow và Agentic: ai quyết định đường đi?

**Workflow automation**
- Các bước đi được lập trình sẵn bằng code.
- Trạng thái được lưu chắc chắn trong database hoặc biến chương trình.
- Vòng lặp dừng khi chạy hết các bước cố định trong code.

**Agentic system**
- Model tự chọn đường đi linh hoạt tại thời điểm chạy.
- Lịch sử chat trong cửa sổ ngữ cảnh do model giữ (rủi ro mất tiến trình rất cao khi đầy context).
- Model tự đánh giá và tuyên bố "tôi đã hoàn thành".

### Ba tiêu chí phân loại mọi hệ thống

1. **Ai quyết định bước tiếp theo?** Đọc code thấy rõ bước kế → workflow. Chỉ lúc chạy mới biết → agent. Đây là tiêu chí nền tảng.
2. **Ai giữ trạng thái?** Qua biến, DB, node graph → hệ thống quản lý. Qua lịch sử hội thoại → model duy trì (đầy rủi ro vì cửa sổ ngữ cảnh có giới hạn).
3. **Ai dừng vòng lặp?** Hết bước trong code → workflow. Model nói "xong rồi" → agent. Agent **bắt buộc** có rào chắn dừng cứng: số vòng, token, thời gian.

### Bảng so sánh

| Ứng dụng | Ai quyết bước sau | Ai giữ state | Ai dừng vòng lặp | Số lần gọi model | Lỗi sai đặc trưng |
|---|---|---|---|---|---|
| Chatbot | Code | Lịch sử hội thoại | Người dùng | 1 / lượt | Nói sai tự tin |
| RAG app | Code | Không có state | Hết 1 chặng | 1 / câu hỏi | Truy vấn trượt |
| Workflow | Code | Hệ thống | Hết bước cố định | Biết trước | Định tuyến sai |
| Agentic | **Model** | Hệ thống (bắt buộc) + model | Trần cứng | Không đoán trước | Lặp vô tận, vượt quyền |

### Vì sao nên ưu tiên kiến trúc workflow

> "You should consider adding complexity only when it demonstrably improves outcomes." — Anthropic

- **Chi phí:** mỗi vòng lặp đều phải gửi lại toàn bộ lịch sử. Agent ≈ 4× token so với chat; multi-agent ≈ 15× (Anthropic, multi-agent research system).
- **Khả năng dự đoán:** workflow gãy ở chặng 3 thì biết ngay là chặng 3. Agent lỗi đòi hỏi đọc trace 20 bước để tìm điểm rẽ sai.
- **Khả năng kiểm thử:** workflow kiểm định bằng unit test. Agent đòi hỏi test qua eval dataset và trajectory.

Chỉ dùng agent khi **không thể** định sẵn các bước. Ví dụ: tự đọc và vá issue, điều tra sự cố production.

> Gartner (25/06/2025): hơn 40% dự án agentic AI sẽ bị huỷ vào cuối 2027. Trong hàng nghìn nhà cung cấp tự xưng làm agentic AI, chỉ khoảng 130 bên có năng lực agentic thật.

### Tổng kết phần 2

- Phân biệt bằng ba tiêu chí: ai chọn bước tiếp theo, ai giữ trạng thái, ai quyết định dừng.
- Workflow: code định sẵn đường đi. Agent: model tự chọn đường đi.
- *Engines run workflows; agents manage workflows.*
- Agent đắt hơn và khó test hơn. Chỉ dùng khi bài toán thực sự không thể xác định các bước từ đầu.

---

## Phần 03 – Cấu trúc Agent

### Công thức trục

```
agent = model + harness
```

**Harness** là toàn bộ cơ chế bao quanh model để biến năng lực ngôn ngữ thành hành vi đáng tin cậy trên hệ thống thật.

> Model cấp năng lực. Harness cấp độ tin cậy.

### Góc nhìn kinh doanh (2026)

- **AI Agent đảm nhận:** khối lượng lớn hàng nghìn tác vụ/ngày; việc lặp lại (nhập liệu, tổng hợp, báo cáo); xử lý dữ liệu tốc độ cao, phân tích, trích xuất; hoạt động 24/7.
- **Con người đảm nhận:** chiến lược, định hướng, quyết định dài hạn; xử lý ngoại lệ và vấn đề chưa có tiền lệ; giao tiếp thấu cảm, xây quan hệ; quyết định cuối và chịu trách nhiệm.

> Human + AI = tối ưu.

### Góc nhìn công nghệ (Addy Osmani, 2026)

> "Agent = Model + Harness. If you're not the model, you're the harness."
> "A decent model with a great harness beats a great model with a bad harness."

Chúng ta không huấn luyện model, nhưng hoàn toàn làm chủ harness. Đó là cơ hội lớn.

### 12 lớp harness

**Nhóm đầu vào**

| # | Lớp | Vai trò | Chặn lỗi gì | Buổi |
|---|---|---|---|---|
| 1 | **context** | Quyết định cái gì được đưa vào cửa sổ ngữ cảnh ở mỗi bước | Model bị nhiễu, chi phí phình | 2, 7 |
| 2 | **tools** | Tập hàm agent được phép gọi, kèm schema và mô tả | Không làm được gì, hoặc làm thứ không nên làm | 5 |
| 3 | **skills** | Gói chỉ dẫn quy trình có tính tái sử dụng cao | Cùng một tác vụ nhưng thiếu nhất quán | 5 |
| 4 | **retrieval** | Cấp tri thức đúng lúc, có trích dẫn | Ảo giác do thiếu dữ liệu, suy luận từ dữ liệu lỗi thời | 6 |

**Nhóm trạng thái và quy trình**

| # | Lớp | Vai trò | Chặn lỗi gì | Buổi |
|---|---|---|---|---|
| 5 | **memory** | Dữ liệu agent lưu giữ trong và giữa các phiên | Hỏi lại thông tin đã biết; nhớ dữ liệu cần xoá | 7 |
| 6 | **state** | Trạng thái tác vụ: đang ở bước nào, đã làm gì, còn gì | Mất tiến trình khi phiên đứt, không resume được | 7, 8 |
| 7 | **workflow** | Node, edge, routing, checkpoint, recovery | Quy trình rối loạn, mất khả năng khôi phục | 8 |
| 8 | **verification** | Kiểm chứng đầu ra: test, schema validation, definition of done | Báo hoàn thành khi task vẫn lỗi | 9 |

**Nhóm an toàn và con người**

| # | Lớp | Vai trò | Chặn lỗi gì | Buổi |
|---|---|---|---|---|
| 9 | **permission** | Phạm vi tài nguyên agent được thao tác | Leo thang đặc quyền, phá hoại dữ liệu | 11 |
| 10 | **logging** | Lưu vết input, output, tool call, lỗi, quyết định | Mất dấu vết điều tra; tin vào lời agent tự khai | 11 |
| 11 | **human approval** | Điểm dừng chờ con người phê duyệt | Thao tác không thể hoàn tác bị kích hoạt tự động | 8, 11 |
| 12 | **handoff** | Bàn giao ngữ cảnh giữa agent, với con người, hoặc qua các phiên | Đứt gãy thông tin tại điểm nối | 10 |

Thứ tự 12 lớp: context · tools · skills · retrieval · memory · state · workflow · verification · permission · logging · human approval · handoff.

### Ba vụ việc thực tế: lớp harness bị thiếu

**Vụ 1 – Cursor, 04/2025: bot hỗ trợ tự bịa chính sách công ty**
- Bot hỗ trợ "Sam" báo cho người dùng một chính sách không tồn tại: mỗi tài khoản chỉ dùng trên một thiết bị. Người dùng tin và huỷ đăng ký.
- Model có lỗi không? Không. Model làm đúng thiết kế: sinh ra một câu nghe hợp lý.
- Thiếu harness: **retrieval, verification, human approval**.
- Nguồn: AI Incident Database #1039.

**Vụ 2 – Air Canada, 02/2024: chatbot nói sai, toà bắt hãng chịu trách nhiệm**
- Moffatt v. Air Canada, 2024 BCCRT 149. Hãng lập luận chatbot là "một thực thể pháp lý riêng biệt". Toà bác bỏ: chatbot nằm trên website của hãng, nên hãng chịu trách nhiệm cho mọi thông tin ở đó.
- "It makes no difference whether the information comes from a static page or a chatbot."
- Output của agent là phát ngôn chính thức của tổ chức.
- Thiếu harness: **retrieval, verification, logging**.

**Vụ 3 – GitHub MCP, 05/2025: prompt injection qua một issue công khai**
1. Kẻ tấn công tạo một issue độc hại trong repo public.
2. Agent được yêu cầu "xem giúp các issue trong repo public" và thực thi chỉ thị ẩn trong issue đó.
3. Agent lấy dữ liệu từ repo private đẩy vào PR trên repo public: rò rỉ dữ liệu.
- "Not a flaw in the GitHub MCP server code itself, but rather a fundamental architectural issue that must be addressed at the agent system level." (Invariant Labs)
- Thiếu harness: **permission, tools, context, logging**. Nguồn: OWASP LLM01 Prompt Injection, hạng mục số một.

**Bài học chung:** không vụ nào giải quyết được bằng đổi model. Nếu ngày mai có model thông minh gấp mười lần, vụ GitHub MCP vẫn không tự được giải quyết. **Quyền hạn không phải là thuộc tính của trí thông minh.**

---

## Phần 04 – Công thức

```
agent = model + harness
```

Không huấn luyện model. Giá trị thực sự nằm ở việc xây dựng harness.

**Tóm tắt buổi 1:** Model quyết định agent *có thể* làm gì. Harness quyết định agent *thực sự* làm gì.

Buổi 2 tiếp theo: nền tảng LLM cho agent (token, context window, structured output, function calling).
