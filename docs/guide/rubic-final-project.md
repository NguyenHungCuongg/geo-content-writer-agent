---
title: "SE373 - Rubric đánh giá đồ án cuối kỳ (A4)"
course: "SE373 Agentic AI Engineering"
created: "2026-10-06"
confidence: "draft"
stage: "BẢN NHÁP v3 chấm theo use case ngang điểm (1,5đ/UC, trần 7,5đ); phần mềm tối đa 2,5đ; nhóm 5 SV"
supersedes: "raw/hcmus/Courses/AgenticAIEngineering/DoAnCuoiKy/2026-10-06_rubric_danh_gia_do_an_cuoi_ky_v2.md"
sources:
  - "raw/hcmus/Courses/AgenticAIEngineering/Curriculum/SE373 - Kỹ thuật xây dựng hệ thống Agentic AI.md (Bảng 8, 9, 10, 11, mục 6)"
  - "raw/hcmus/Courses/AgenticAIEngineering/00_Course_Overview.md (mục 5, 7)"
---

# SE373 - Rubric đánh giá đồ án cuối kỳ (A4)

Đồ án cuối kỳ (A4) chiếm 50% điểm môn. Bài làm theo nhóm 5 sinh viên (khoảng 50 nhóm cho lớp 250 SV). Mỗi nhóm chọn 1 trong 10 đề tài:

| #  | Đề tài                    | #  | Đề tài                 |
|----|---------------------------|----|------------------------|
| 1  | Coding Agent              | 6  | IELTS Learning Agent   |
| 2  | Code review agent         | 7  | Business Ops Agent     |
| 3  | Helpdesk Agent            | 8  | Tour Guide Agent       |
| 4  | GEO content writer Agent  | 9  | Analytics Agent        |
| 5  | Interview Agent           | 10 | AI Training Agent      |

**Thay đổi so với v2:**
*   Bỏ phân loại use case "bắt buộc / nâng cao". Mỗi đề tài đưa ra một danh sách use case, mọi use case ngang điểm: 1,5 điểm.
*   Phần agent tính theo tổng điểm các use case, tối đa 7,5 điểm.
*   Phần mềm giảm từ tối đa 3,0 xuống tối đa 2,5 điểm.
*   Chất lượng harness không còn chấm thành một khối riêng. Nó được chấm bên trong từng use case, kèm quy tắc các use case phải phủ đủ 8 mảng kiến thức của môn.

---

## 1. Cấu trúc điểm

| Phần | Nội dung | Điểm |
|---|---|---|
| **I. Phần mềm** | Ứng dụng có tích hợp agent (desktop, web hoặc CLI, nhóm tự chọn) | Tối đa 2,5 |
| **II. Agent** | Tổng điểm các use case nhóm hoàn thành, mỗi UC tối đa 1,5 điểm | Tối đa 7,5 |
| **Tổng điểm nhóm** | | **10,0** |

**Điểm cá nhân** = Điểm nhóm $\times$ Hệ số vấn đáp (mục 6). Điều kiện bắt buộc và các khoản trừ điểm ở mục 5.

**Nguyên tắc:**
*   **Phần I** chấm sản phẩm phần mềm bao quanh agent. Nhóm được tự do sáng tạo, nhưng phần này không vượt quá 2,5 điểm.
*   **Phần II** chấm agent. Một chức năng chỉ được tính ở Phần II khi agent thực hiện nó, không phải code thông thường làm thay.
*   **Làm nhiều hơn để bù rủi ro:** 5 UC đạt trọn điểm là đủ 7,5. Nhóm được làm thêm UC: điểm Phần II là tổng điểm mọi UC đã nộp, chặn trần ở 7,5. Một UC chỉ đạt một phần có thể được bù bằng UC khác.

---

## 2. Cách tổ chức yêu cầu đề tài

### 2.1. Danh sách use case
Mỗi đề tài đưa ra 8-11 use case ngang điểm, không phân bắt buộc hay nâng cao. Nhóm chọn các UC sẽ làm. Có hai ràng buộc:
1.  **Phủ kiến thức (mục 2.2):** tập UC nhóm nộp phải phủ đủ 8 mảng kiến thức K1-K8.
2.  **Sở hữu:** mỗi SV sở hữu ít nhất 1 UC và chịu trách nhiệm UC đó từ đầu đến cuối: code, eval case, trace, trả lời vấn đáp. Nhóm 5 SV làm 5 UC là vừa đủ trần điểm; làm 6-7 UC để có dư phòng.

### 2.2. 8 mảng kiến thức và quy tắc phủ
Mỗi UC trong mô tả đề tài được gắn 1-3 mảng kiến thức chính. Mảng chính được chấm ở tiêu chí U2 của UC đó (mục 4.1).

| Mã | Mảng kiến thức | Buổi | CĐRMH |
|:---:|---|:---:|---|
| **K1** | Tích hợp model, structured output, agent loop, kiến trúc model + harness | 2, 3, 4 | G2.1, G3.1 |
| **K2** | Tool use và agent skills | 5 | G2.3, G3.2 |
| **K3** | RAG/knowledge harness | 6 | G3.3, G2.2 |
| **K4** | Memory, state, context | 7 | G2.2 |
| **K5** | Workflow orchestration, human-in-the-loop | 8 | G4.1 |
| **K6** | Multi-agent hoặc MCP | 10 | G4.2 |
| **K7** | Verification và evaluation | 9 | G5.1 |
| **K8** | Security, governance, observability | 11 | G6.1, G6.2, G5.1 |

**Quy tắc phủ:** gộp các mảng chính của tất cả UC nhóm nộp, kết quả phải đủ K1-K8. Thiếu mỗi mảng, trừ 0,5 điểm vào Phần II (sau khi đã chặn trần 7,5).
*Khi viết danh sách UC cho mỗi đề tài, giảng viên bảo đảm mỗi mảng K xuất hiện ở ít nhất 2 UC, để nhóm luôn có lựa chọn.*

### 2.3. Quy tắc viết mỗi use case
Mỗi UC trong mô tả đề tài có đủ 6 mục:
1.  **Mô tả:** tình huống, đầu vào, đầu ra mong đợi.
2.  **Mảng kiến thức chính (K):** 1-3 mảng.
3.  **Yêu cầu kỹ thuật:** những gì harness phải có.
4.  **Tiêu chí chấp nhận:** 3-6 tiêu chí kiểm thử được, có ngưỡng rõ ràng.
5.  **Eval case tối thiểu:** ít nhất 5 case, trong đó có ít nhất 1 case biên hoặc case lỗi.
6.  **Bằng chứng nộp:** trace của ít nhất 1 lần chạy thành công.

### 2.4. Yêu cầu nền chung (áp cho toàn hệ thống)
Các yêu cầu này lấy từ Bảng 8 đề cương. Chúng không có điểm riêng, nhưng được kiểm ở vòng 1 (mục 7). Vi phạm thì trừ điểm theo mục 5, hoặc kéo điểm U2/U3 của các UC liên quan xuống.

| HR | Yêu cầu |
|:---:|---|
| **HR-01** | Gọi LLM API hoặc model local; báo cáo nêu giới hạn của model đã chọn |
| **HR-02** | Có workflow từ 3 node trở lên, có điều kiện dừng |
| **HR-03** | Có sơ đồ kiến trúc agent = model + harness, chỉ rõ từ 4 lớp harness trở lên; có bảng failure mode và cơ chế giảm rủi ro |
| **HR-04** | Có ít nhất 1 công cụ ngoài; có ít nhất 2 skill dùng lại được với contract đầy đủ |
| **HR-05** | Mọi lần chạy đều có log/trace: input, output, tool call, skill invocation, lỗi, quyết định |
| **HR-06** | Tập eval chung chạy được bằng một lệnh; tổng tối thiểu 5 case $\times$ số UC + 5 case tấn công (ví dụ 5 UC thì tối thiểu 30 case); chạy regression ít nhất 2 lần (trước và sau cải tiến) |
| **HR-07** | Repo có README, `.env.example`, báo cáo kỹ thuật, video demo, bảng phân công ghi người sở hữu từng UC, mục minh bạch sử dụng AI và trích dẫn nguồn |

---

## 3. Rubric Phần I - Phần mềm (tối đa 2,5 điểm)

Hình thức tự chọn: desktop app, web app hoặc CLI app. Ứng dụng phải tích hợp agent thật: người dùng thao tác trên app, app gọi agent, hiển thị tiến trình và kết quả. Một app chỉ là khung chat bọc ngoài API của LLM thì không được tính.

| Tiêu chí | Điểm | Giỏi | Khá | Trung bình | Yếu |
|---|:---:|---|---|---|---|
| **1.1. Sáng tạo** | 0,5 | Ý tưởng sản phẩm khác biệt, giải quyết đúng nỗi đau người dùng; đưa agent vào trải nghiệm theo cách mới (không chỉ là khung chat) | Có điểm khác biệt rõ ở một vài tính năng hoặc cách tương tác | Đúng đề tài nhưng cách làm phổ biến | Sao chép mẫu có sẵn |
| **1.2. Độ phức tạp kỹ thuật** | 0,75 | Kiến trúc nhiều thành phần (frontend/backend/DB hoặc tương đương), xử lý bất đồng bộ, streaming hoặc cập nhật trạng thái agent theo thời gian thực, quản lý phiên | Tách lớp rõ, có lưu trữ dữ liệu, gọi agent qua API nội bộ | Ứng dụng một khối, luồng đơn giản | Script chạy một lần hoặc giao diện tĩnh |
| **1.3. Độ hoàn thiện** | 0,75 | Chạy ổn định trong demo; xử lý tốt trạng thái chờ, lỗi, trùng dữ liệu; hiển thị tiến trình agent, màn hình phê duyệt và trace; README cài đặt chạy được ngay; có test cho phần mềm | Ổn định ở luồng chính, xử lý phần lớn lỗi thường gặp | Chạy được nhưng còn lỗi giao diện hoặc thiếu xử lý lỗi | Không chạy ổn định trong demo |
| **1.4. Khối lượng** | 0,5 | Có giao diện cho mọi UC đã nộp, kèm tính năng phụ trợ (lịch sử, quản lý dữ liệu, cấu hình, dashboard eval...) | Có giao diện cho mọi UC đã nộp | Có giao diện cho phần lớn UC | Chỉ có giao diện cho 1-2 UC |

*Mỗi tiêu chí chấm theo 4 mức. Hệ số áp vào trọng số: Giỏi 100% - Khá 75% - Trung bình 50% - Yếu 0-25%.*

---

## 4. Rubric Phần II - Agent (tối đa 7,5 điểm)

### 4.1. Chấm từng use case (1.5 điểm mỗi UC)
Mỗi UC chấm theo 3 tiêu chí, mỗi tiêu chí 0,5 điểm, theo 4 mức: Giỏi 100% - Khá 75% - Trung bình 50% - Yếu 0-25%.

| Tiêu chí | Điểm | Giỏi | Khá | Trung bình | Yếu |
|---|:---:|---|---|---|---|
| **U1. Chức năng**<br>(UC có chạy đúng không) | 0,5 | Đạt mọi tiêu chí chấp nhận; demo trực tiếp ổn định | Đạt phần lớn tiêu chí, còn lỗi ở case biên | Chỉ chạy được luồng chuẩn, nhiều tiêu chí chưa đạt | Không chạy, không có bằng chứng, hoặc kết quả do code cứng tạo ra |
| **U2. Thiết kế harness**<br>(Các mảng K chính của UC được làm đúng kỹ thuật đến đâu) | 0,5 | Đạt mức Giỏi của mọi mảng K chính gắn với UC (mô tả ở mục 4.2) | Mức Khá | Mức Trung bình | Mức Yếu |
| **U3. Kiểm chứng**<br>(UC được đánh giá và quan sát ra sao) | 0,5 | Đủ $\ge$ 5 eval case, có case biên, có số liệu đúng/sai, có trace, phân tích được case thất bại, có so sánh regression | Đủ eval case và trace, phân tích lỗi còn sơ sài | Có vài eval case, thiếu số liệu hoặc trace | Không có eval case hoặc trace |

*Ví dụ tính điểm: Nhóm nộp 6 UC, điểm lần lượt 1,5 - 1,5 - 1,25 - 1,5 - 1,0 - 1,25 (Tổng $= 8,0$), chặn trần còn $7,5$. Tập UC thiếu mảng K6, trừ $0,5$. Phần II điểm $= 7,0$.*

### 4.2. Mô tả mức độ của 8 mảng kiến thức (dùng để chấm U2)

**K1. Tích hợp model, structured output, agent loop, kiến trúc**
*   **Giỏi:** Structured output hoặc function calling có validation theo schema, tự sửa khi output sai. Agent loop có mục tiêu, quan sát, hành động, điều kiện dừng, giới hạn số vòng. Phần của UC trong sơ đồ kiến trúc khớp với code.
*   **Khá:** Đủ thành phần chính, nhưng xử lý output sai hoặc điều kiện dừng chưa chặt.
*   **Trung bình:** Chạy được luồng cơ bản; validation hạn chế.
*   **Yếu:** Chỉ gọi LLM một lần, không validation, không có vòng lặp agent.

**K2. Tool use và agent skills**
*   **Giỏi:** Tool có schema rõ, có retry, timeout, xử lý lỗi. Skill có contract đầy đủ (metadata, chỉ dẫn, đầu vào đầu ra, ràng buộc, ví dụ, final check) và dùng lại được. Trace chứng minh agent chọn đúng tool hoặc skill.
*   **Khá:** Contract và xử lý lỗi cơ bản đủ, nhưng khả năng tái sử dụng chưa tốt.
*   **Trung bình:** Contract đơn giản, thiếu final check, đôi khi cần can thiệp thủ công.
*   **Yếu:** Tool hoặc skill không chạy, không có contract.

**K3. RAG/knowledge harness**
*   **Giỏi:** Đủ các bước ingestion, chunking hợp lý, embedding, vector store, retrieval có metadata. Câu trả lời grounded, citation chính xác; thiếu tri thức thì báo không đủ thông tin. Có đo chất lượng retrieval và phân tích case thất bại.
*   **Khá:** Chạy đúng, có citation, chưa đo hoặc chưa tối ưu retrieval.
*   **Trung bình:** Citation thiếu hoặc sai; có hallucination khi thiếu tri thức.
*   **Yếu:** Câu trả lời không dựa trên kho tri thức.

**K4. Memory, state, context**
*   **Giỏi:** Lưu task state và progress log; resume được sau khi tắt chương trình. Có chiến lược compaction, giữ đủ mục tiêu, ràng buộc, trạng thái, rủi ro đang mở và bước tiếp theo; có kiểm tra sau compaction. Có quy định về dữ liệu cá nhân và thời gian lưu giữ nếu có bộ nhớ dài hạn.
*   **Khá:** Có state và resume; compaction đơn giản hoặc chưa kiểm tra.
*   **Trung bình:** Chỉ nhớ trong một phiên; resume làm mất thông tin.
*   **Yếu:** Không quản lý state; agent quên mục tiêu giữa chừng.

**K5. Workflow orchestration, human-in-the-loop**
*   **Giỏi:** Workflow có state, routing, branching, checkpoint, recovery khi một node lỗi. Có điểm phê duyệt của người chặn đúng các hành động rủi ro; duyệt xong thì tiếp tục đúng chỗ. Tiêu chí hoàn thành chính xác.
*   **Khá:** Đủ thành phần chính; recovery hoặc phê duyệt còn đơn giản.
*   **Trung bình:** Chạy tuyến tính, thiếu xử lý ngoại lệ.
*   **Yếu:** Sai luồng, hoặc không có điều kiện dừng.

**K6. Multi-agent hoặc MCP**
*   **Giỏi:** Mô tả rõ vai trò, interface, quyền truy cập của từng agent hoặc thành phần MCP. Các bên phối hợp đúng và trao đổi kết quả thật. Có coordination trace; quyền được kiểm soát.
*   **Khá:** Có phân vai và chạy được; trace hoặc kiểm soát quyền chưa đủ.
*   **Trung bình:** Phối hợp chưa ổn định, hoặc multi-agent chỉ mang tính hình thức.
*   **Yếu:** Các thành phần không phối hợp được.

**K7. Verification và evaluation**
*   **Giỏi:** Có definition of done cho UC, có bộ kiểm tra tự động (test, validator hoặc evaluator agent). Đánh giá được chất lượng, chi phí, độ trễ; regression trước và sau cải tiến có số liệu.
*   **Khá:** Có kiểm tra tự động và số liệu chính; regression chưa đủ.
*   **Trung bình:** Kiểm tra thủ công là chính; thiếu số liệu.
*   **Yếu:** Không có cơ chế kiểm chứng.

**K8. Security, governance, observability**
*   **Giỏi:** Mô tả quyền hạn của từng tool liên quan. Áp dụng và kiểm thử hiệu quả ít nhất 1 biện pháp (least privilege, allowlist, sandbox, approval gate, guardrail, audit log). Có case thử prompt/skill injection, kèm kết quả và cách xử lý. Trace tra cứu được.
*   **Khá:** Có biện pháp kiểm soát; kiểm thử injection hoặc minh chứng hiệu quả chưa đủ.
*   **Trung bình:** Biện pháp mang tính hình thức, chưa kiểm thử.
*   **Yếu:** Không kiểm soát, hoặc có hành vi không an toàn mà không được phân tích.

---

## 5. Điều kiện bắt buộc và điểm trừ

| Tình huống | Xử lý |
|---|---|
| - Agent không chạy được trong demo và không có video hoặc trace dự phòng<br>- Tập UC nộp thiếu mảng kiến thức (mục 2.2)<br>- Không có tập eval chạy được (HR-06) | - U1 của các UC liên quan $= 0$<br>- Trừ 0,5 điểm Phần II cho mỗi mảng thiếu<br>- U3 của mọi UC tối đa mức Yếu |
| Lộ API key, token hoặc mật khẩu trong repo | Trừ 1,0 điểm tổng |
| Thiếu `.env.example` hoặc hướng dẫn cấu hình an toàn | Trừ 0,25 điểm tổng |
| Tool hoặc skill chạy lệnh nguy hiểm mà không có approval gate | U2 của UC liên quan $= 0$ |
| Không minh bạch việc dùng AI, không trích dẫn nguồn | Trừ 0,5 điểm tổng; nếu nghiêm trọng thì xử lý như gian lận |
| Vi phạm quy định riêng của đề tài (ví dụ dùng sản phẩm agent có sẵn làm hộ) | UC liên quan $= 0$ |
| Sao chép bài, dùng chung repo, giả mạo commit, nộp sản phẩm không hiểu được | 0 điểm A4, xử lý theo quy định của Khoa và Trường (mục 6 đề cương) |

---

## 6. Hệ số vấn đáp (điểm cá nhân)

Vòng 3 vấn đáp kéo dài 15-20 phút mỗi nhóm (khoảng 3-4 phút mỗi SV). Mỗi thành viên trả lời trước hết về UC mình sở hữu, sau đó phải giải thích được: kiến trúc model + harness, thiết kế agent và skill, luồng xử lý, cách đánh giá và giới hạn của giải pháp. Bằng chứng đóng góp gồm lịch sử commit, bảng phân công và task board.

| Mức | Biểu hiện | Hệ số |
|---|---|:---:|
| **Nắm vững** | Giải thích đúng, sâu UC mình sở hữu; trả lời được câu hỏi về phần của thành viên khác | **1,0** |
| **Nắm được** | Giải thích đúng, còn lúng túng ở UC của mình, phần chung | **0,8** |
| **Nắm sơ sài** | Chỉ mô tả bề mặt, không giải thích được thiết kế hoặc code | **0,5** |
| **Không nắm** | Không giải thích được phần việc được giao, hoặc không có đóng góp | **0 - 0,3** |

---

## 7. Quy trình chấm 3 vòng

| Vòng | Hình thức | Chấm gì |
|---|---|---|
| **1. Checklist tự động trên repo** | CI của GitHub Classroom | HR-01 đến HR-07: README, `.env.example`, quét khoá bị lộ, tập eval chạy được và đủ số case, file skill đủ trường contract, bảng phân công; kiểm tra quy tắc phủ K1-K8 |
| **2. Video demo bắt buộc** | Video $\le$ 15 phút, demo mọi UC đã nộp | U1 từng UC; tiêu chí 1.3, 1.4 |
| **3. Vấn đáp theo ca** | 15-20 phút mỗi nhóm, trợ giảng chủ trì; giảng viên dự các nhóm có điểm cao hoặc thấp bất thường | U2, U3 từng UC (đối chiếu báo cáo, trace với lời giải thích); tiêu chí 1.1, 1.2; hệ số vấn đáp |

---

## 8. Ánh xạ về đề cương

| CĐRMH (Bảng 11) | Nơi được chấm |
|---|---|
| **G2.1, G3.1** | U2 của các UC gắn K1; U1 mọi UC |
| **G2.2** | U2 của các UC gắn K3, K4 |
| **G2.3, G3.2** | U2 của các UC gắn K2; Phần I (tích hợp agent vào ứng dụng) |
| **G3.3** | U2 của các UC gắn K3 |
| **G4.1** | U2 của các UC gắn K5 |
| **G4.2** | U2 của các UC gắn K6 |
| **G5.1** | U3 mọi UC; U2 của các UC gắn K7 |
| **G6.1, G6.2** | U2 của các UC gắn K8; mục 5; vấn đáp |

*Nhờ quy tắc phủ (mục 2.2), mọi CĐRMH của A4 đều được chấm ở mọi nhóm.*