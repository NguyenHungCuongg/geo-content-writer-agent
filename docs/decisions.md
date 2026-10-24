# Nhật ký quyết định

Mỗi quyết định ghi: đã chọn gì, vì sao, và hệ quả cần nhớ. Phần "vì sao" dùng cho báo cáo kỹ thuật và vấn đáp. Đổi quyết định thì thêm mục mới, ghi `Thay thế D-xx`, và đánh dấu mục cũ là `Đã bị thay thế bởi D-yy`; không xoá mục cũ.

## D-01. Thương hiệu: Skyveil, sơn và vật liệu chống nóng mái nhà (23/10/2026)

**Vì sao chọn ngách này**
- Có nhiều số liệu tier A cho fact-checker (UC-04): QCVN 09 của Bộ Xây dựng về công trình sử dụng năng lượng hiệu quả, số liệu nắng nóng của Trung tâm Dự báo KTTV quốc gia, biểu giá điện EVN.
- Số liệu thay đổi theo năm (nắng nóng, giá điện), nên dễ tạo bài lỗi thời cho UC-08.
- Nhiều nội dung dạng hướng dẫn thi công từng bước, hợp với schema `HowTo` và FAQ ở UC-06.
- Intent commercial và transactional rõ ràng, phù hợp đo visibility ở UC-07.

**Vì sao không dùng tên CoolMax:** trùng thương hiệu thật trong cùng ngách, gồm tôn COLORBOND® Coolmax® của BlueScope, sơn Captain Parashield Coolmax ở Thái Lan, và nhãn hiệu vải COOLMAX® của The LYCRA Company. Như vậy vi phạm đặc tả mục 1.5.2, và answer engine sẽ nhầm với sản phẩm thật khi đo visibility. Đã tra "Skyveil" trên web ngày 23/10/2026, không thấy trùng.

**Hệ quả**
- Tên đối thủ hư cấu cũng phải tra như vậy trước khi đưa vào brand kit.
- Các claim dạng "giảm X°C", "tiết kiệm Y% điện" trong brand kit phải có bằng chứng. Fact-checker phải xếp những claim không có nguồn tier A vào `unverifiable`.
- Site WordPress thử nghiệm đặt noindex (đặc tả mục 2.4).

## D-02. LLM: Google AI Studio (Gemini) (23/10/2026)

**Đã chọn:** gọi Gemini qua Google AI Studio bằng SDK chính thức `google-genai`. Tên model đọc từ biến môi trường `GEMINI_MODEL`, tên model embedding đọc từ `GEMINI_EMBED_MODEL`, chưa cố định model cụ thể.

**Hệ quả**
- Không ghi tên model cứng trong code. Đổi model chỉ cần sửa `.env`, và mỗi lần chạy eval phải ghi tên model vào kết quả để so sánh regression.
- Gói miễn phí có giới hạn số request mỗi phút, nên eval và batch đo visibility cần cache và retry có backoff (UC-07 tiêu chí 5).
- Báo cáo phải nêu giới hạn của model đã chọn (HR-01).
- Phase 2 dùng LangGraph thì gọi Gemini qua `langchain-google-genai`.

## D-03. Ứng dụng: FastAPI + React (Vite) (23/10/2026)

**Vì sao:** frontend, backend và DB tách riêng, cộng với streaming tiến trình agent, là các điều kiện để đạt mức Giỏi ở tiêu chí 1.2 của rubric. Các màn hình đề yêu cầu (duyệt bài ở UC-10, fact-check theo từng câu ở UC-04, biểu đồ trước/sau ở UC-07) cũng cần một web UI thật.

**Hệ quả:** backend stream sự kiện của agent bằng SSE. Frontend chỉ đọc API, không gọi LLM trực tiếp.

## D-04. Database: Postgres + pgvector (23/10/2026)

**Vì sao không dùng SQLite:** web app chạy agent nền và stream kết quả sẽ ghi đồng thời, mà SQLite chỉ cho một luồng ghi tại một thời điểm. Postgres + pgvector dùng một DB cho cả bốn việc: dữ liệu app, checkpointer LangGraph (`langgraph-checkpoint-postgres`), vector store và tìm theo từ khoá. Docker cũng đã cần sẵn để chạy WordPress.

**Hệ quả**
- Full-text search của Postgres không có từ điển tiếng Việt: dùng config `simple` + `unaccent`, hoặc tính BM25 bằng Python rồi trộn với pgvector bằng RRF.
- Eval nạp lại dữ liệu vào schema riêng trước mỗi lần chạy để kết quả tái lập được.
- Phase 1 (UC-01) chưa cần DB. Postgres được thêm vào `docker-compose.yml` ở Phase 2.

## D-05. Tập UC nộp: UC-01, 02, 03, 04, 07 (23/10/2026, được bổ sung bởi D-06)

**Đã chọn:** UC-01 (K1), UC-02 (K2, K3, K8), UC-03 (K1, K2), UC-04 (K3, K6, K7), UC-07 (K2, K4, K7). Đã đăng ký với GVTH. Phase 1 làm UC-01.

**Vì sao:** năm UC này nối thành một pipeline liền mạch: sinh prompt → nghiên cứu nguồn → viết bài → fact-check → đo visibility. Kết quả của UC trước là đầu vào của UC sau.

**Hệ quả**
- **Thiếu K5**: bị trừ 0,5 điểm Phần II nếu không bổ sung. Phase 2 cũng bắt buộc có workflow LangGraph với bước người duyệt, mà chưa UC nào có. Đề xuất thêm UC-10 (K5, K8), vừa phủ K5 vừa dư phòng thành 6 UC.
- Chỉ có 5 UC nên không còn dư: một UC mất điểm là tổng điểm Phần II giảm theo.

## D-06. Thêm UC-10: duyệt và xuất bản WordPress (23/10/2026, đã bị thay thế bởi D-07)

**Tập UC sau khi bổ sung:** 01, 02, 03, 04, 07, 10. Phủ đủ K1-K8; 6 UC nên có 1 UC dư phòng.

**Vì sao:** UC-10 (K5, K8) bù mảng K5 còn thiếu. Approval gate của UC-10 cũng chính là "bước người duyệt" mà Phase 2 bắt buộc.

**Hệ quả**
- Phase 2 cần WordPress chạy bằng Docker. Site đặt noindex, REST API bật, tạo user riêng cho agent với quyền thấp nhất đủ dùng, xác thực bằng Application Password (đặc tả mục 2.4).
- `.env.example` thêm các biến WordPress (URL, user, Application Password) khi bắt đầu UC-10. Agent không bao giờ đọc hay in Application Password.
- Frontend cần màn hình duyệt bài: bản xem trước, báo cáo fact-check (UC-04), URL đích, các nút Duyệt / Từ chối / Sửa rồi duyệt.
- Báo lại GVTH vì tập UC đã đăng ký thay đổi.

## D-07. Tập UC chính: UC-01, 02, 03, 04, 09; UC-07 và UC-10 là dự phòng (23/10/2026, thay thế D-06)

**Tập chính:** UC-01 (K1), UC-02 (K2, K3, K8), UC-03 (K1, K2), UC-04 (K3, K6, K7), UC-09 (K4, K5). Năm UC này đã phủ đủ K1-K8.

**Vì sao:** nhóm muốn 5 UC chính tự phủ đủ K1-K8, để mỗi SV sở hữu đúng 1 UC và tập nộp không phụ thuộc vào UC thứ 6.

**Dự phòng** (thêm khi có thời gian, theo thứ tự ưu tiên):
1. UC-07, đo AI visibility: phần cốt lõi của GEO và là demo trực quan nhất.
2. UC-10, duyệt và xuất bản WordPress: các hệ quả kỹ thuật vẫn như D-06.

Chỉ đưa UC dự phòng vào bản nộp khi nó đã có ≥ 5 eval case, trace, màn hình trên app và có mặt trong video demo.

**Hệ quả**
- Không còn UC dư: điểm mất ở bất kỳ UC chính nào là mất hẳn khỏi Phần II, cho tới khi có UC dự phòng bù vào.
- UC-09 không có sẵn bước người duyệt, mà Phase 2 bắt buộc có. Pipeline viết bài trong UC-09 phải có node approval trước khi bài chuyển từ `review` sang `approved`.
- UC-09 chạy lại UC-03 và UC-04 cho từng bài (≥ 8 bài), nên UC-03 và UC-04 phải ổn định trước. Vì gọi Gemini nhiều lần, cần cache và retry khi gặp lỗi 429.
- Báo GVTH tập UC mới.

## D-08. Brand kit Skyveil: khu vực, giọng văn, đối thủ hư cấu (24/10/2026)

**Đã chọn**
- Khu vực: thi công ở TP.HCM (gồm khu vực Bình Dương cũ), Đồng Nai, Tây Ninh (khu vực Long An cũ); xưởng ở khu vực Bình Dương cũ; bán vật liệu online toàn quốc. Địa danh theo đơn vị hành chính sau 1/7/2025.
- Tên sản phẩm: mã model gắn tên thương hiệu (Skyveil R200, D500, P100, F155). Tên mô tả ban đầu trùng sản phẩm thật: Deckshield là hệ phủ sàn của Flowcrete, "Cool Roof" là tên dòng sơn của Dulux Acratex.
- Xưng hô: thương hiệu tự xưng "Skyveil", gọi người đọc "anh/chị".
- Đối thủ hư cấu: Nimbara, Sơn Mây Thạch, Thiên Lam Coating. Đã tra web ngày 24/10/2026, không thấy doanh nghiệp hay sản phẩm sơn thật nào trùng tên.

**Vì sao:** Đông Nam Bộ nắng nóng quanh năm và có nhiều nhà xưởng mái tôn, nên persona và claim cụ thể được. "Anh/chị" hợp cả chủ nhà lẫn chủ xưởng (B2B), không khô như "quý khách".

**Hệ quả**
- Bằng chứng của `approved_claims` là tài liệu nội bộ hư cấu, không phải nguồn tier A hay B. Theo quy tắc bằng chứng của UC-04, claim có số liệu chỉ dựa vào brand kit (ví dụ "thấp hơn 15-20°C") sẽ bị xếp `unverifiable` và phải gỡ hoặc chuyển thành câu định tính. **Chưa chốt:** owner UC-04 quyết định có cho brand kit làm căn cứ cho claim về chính thương hiệu hay không.
- Brand voice cho phép so sánh khách quan với đối thủ (cần cho eval case bài commercial của UC-03), chỉ cấm chê bai, bôi nhọ (đặc tả mục 1.5.7).
- `forbidden_claims` là đáp án cho các case claim quá đà ở eval UC-01 và UC-04.
- Thêm đối thủ mới thì tra tên như trên rồi ghi vào mục này.

## D-09. Nhận diện "nhắc thương hiệu" trong PromptSet của UC-01 (24/10/2026)

**Đã chọn:** một prompt tính là nhắc thương hiệu (`mentions_brand = true`) khi nó chứa một trong các cụm sau (không phân biệt hoa thường):
- tên thương hiệu trong `BrandProfile.name`, cả bản đã bỏ loại hình doanh nghiệp ở đầu ("Công ty TNHH Skyveil" → "Skyveil");
- mã sản phẩm riêng của thương hiệu, lấy từ tên sản phẩm theo mẫu chữ in hoa + số (R200, D500, P100, F155).

Danh sách do `brand_terms(profile)` trong `agent/uc01.py` sinh ra, và validator của `PromptSet` kiểm `mentions_brand` theo danh sách đó.

**Vì sao:** tiêu chí 4 của UC-01 cần đo AI có *tự* nhắc tới Skyveil hay không. Câu "Sơn R200 giá bao nhiêu?" đã lộ thương hiệu dù không có chữ "Skyveil" (tên sản phẩm theo D-08 là mã model gắn tên thương hiệu). Nếu LLM trích tên pháp lý dài, so khớp nguyên chuỗi sẽ bỏ sót các câu chỉ dùng tên ngắn.

**Hệ quả**
- Tên có hậu tố (ví dụ "Skyveil Việt Nam") chưa được rút gọn; Task 4 có thể lấy alias từ brand kit để bổ sung.
- Eval của UC-01 (Task 8) dùng lại `brand_terms` khi chấm tiêu chí 4.
