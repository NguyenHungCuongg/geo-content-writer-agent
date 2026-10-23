# ĐỒ ÁN CUỐI KỲ - SE373
*Tài liệu tham khảo: 2026-10-07_SE373_DoAn_GioiThieu.pdf*

---

## 1. LỘ TRÌNH THỰC HIỆN
Đồ án được chia làm 3 phase (giai đoạn). 
*Lưu ý: Cuối mỗi phase yêu cầu gắn tag trên repo và nộp video demo ngắn. Mỗi phase chỉ dùng kiến thức đã học đến thời điểm đó.*

### PHASE 1: Bootstrap dự án
*   **Thời gian:** 07/10 - 27/10 (3 tuần - Hạn cuối: tuần 7)
*   **Phạm vi kiến thức:** Buổi 1 - 5
*   **Công việc cần làm:**
    *   Đăng ký nhóm 5 Sinh viên, đề tài, use case và người sở hữu.
    *   Khởi tạo repo, CI, codebase ứng dụng và codebase agent.
    *   Agent loop với $\ge 2$ tool, 1 skill, có log từng bước.
    *   1 use case chạy được từ ứng dụng tới agent, $\ge 10$ eval case.

### PHASE 2: Mở rộng năng lực
*   **Thời gian:** 28/10 - 10/11 (2 tuần - Hạn cuối: tuần 9)
*   **Phạm vi kiến thức:** Buổi 6 - 8
*   **Công việc cần làm:**
    *   RAG có trích dẫn nguồn.
    *   Lưu state, dừng rồi chạy tiếp được, nén context.
    *   Workflow LangGraph, có bước người duyệt.
    *   $\ge 3$ use case chạy được.

### PHASE 3: Hoàn thiện và nộp
*   **Thời gian:** 11/11 - 06/12 (3 tuần - Hạn cuối: tuần 12)
*   **Phạm vi kiến thức:** Buổi 9 - 11
*   **Công việc cần làm:**
    *   Tập eval đầy đủ, chạy lại để so sánh.
    *   Multi-agent hoặc MCP.
    *   Kiểm thử an toàn, xem được trace.
    *   $\ge 5$ use case phủ đủ 8 mảng kiến thức; báo cáo, video.

---

## 2. HÌNH THỨC TRÌNH BÀY
Bao gồm hai buổi trình bày: chấm trong pool trước, sau đó trình bày trước toàn lớp. 
*Lưu ý chung: Mỗi thành viên phải trình bày được use case mình sở hữu và trả lời câu hỏi về thiết kế agent.*

### BUỔI 1: Trình bày trong nhóm nhỏ
*   **Quy mô:** 1 pool = 10 nhóm, do 1 Giảng viên thực hành (GVTH) hướng dẫn.
*   **Nội dung:** 
    *   Mỗi nhóm trình bày và demo trước pool của mình.
    *   GVTH phụ trách pool hướng dẫn và chấm điểm.
*   **Kết quả:** Mỗi pool chọn ra **2 đề tài tốt nhất**.

### BUỔI 2: Trình bày trước cả lớp
*   **Quy mô:** 10 đề tài tốt nhất từ các pool.
*   **Nội dung:** 
    *   Các đề tài được chọn trình bày và demo trước cả lớp.
    *   Trình bày và chấm trong buổi chung của lớp.
    *   Cả lớp xem 10 bài toán agent xuất sắc nhất.

---

## 3. TÍNH ĐIỂM
Đồ án chiếm **50% điểm môn học**, được chấm trên thang điểm 10. Điểm bao gồm 2 phần chính:

### Phần Agent (Tối đa 7,5 điểm)
Yêu cầu 5 use case trọn điểm là đủ 7.5 điểm. Có thể làm thêm để bù cho các use case chưa trọn điểm. 
Mỗi use case tương đương **1,5 điểm**, chấm theo 3 tiêu chí:
*   **0,5 điểm:** Chức năng (chạy đúng tiêu chí).
*   **0,5 điểm:** Thiết kế harness (đúng kỹ thuật).
*   **0,5 điểm:** Kiểm chứng (eval, trace).

### Phần mềm (Tối đa 2,5 điểm)
Ứng dụng Desktop, Web hoặc CLI; yêu cầu phải tích hợp agent thật. Chấm theo 4 tiêu chí:
*   **Sáng tạo:** 0,5 điểm
*   **Độ phức tạp kỹ thuật:** 0,75 điểm
*   **Độ hoàn thiện:** 0,75 điểm
*   **Khối lượng:** 0,5 điểm

### Các quy định khác về điểm số
*   **Phủ đủ 8 mảng kiến thức:** Các use case nộp phải phủ đủ từ $K1-K8$. Thiếu mỗi mảng bị trừ **0,5 điểm**.
*   **Điểm cá nhân:** Bằng Điểm nhóm $\times$ hệ số vấn đáp $(0-1,0)$ của từng thành viên.
*   **Vi phạm:** 
    *   Lộ API key: trừ **1,0 điểm**.
    *   Sao chép, gian lận: **0 điểm** toàn bộ đồ án.

---

## 4. DANH SÁCH ĐỀ TÀI ĐĂNG KÝ
Có 10 đề tài để đăng ký. Yêu cầu chi tiết và danh sách use case cụ thể cần xem trong tài liệu riêng của từng đề tài.

| # | Đề tài | Mô tả | Giảng Viên Thực Hành |
|:---:|:---|:---|:---|
| **1** | Coding Agent | Phân loại issue, sửa bug theo vòng lặp chạy test, làm tính năng nhiều bước; reviewer agent kiểm tra trước khi bàn giao. | NHNghĩa |
| **2** | Code review agent | Comment trực tiếp lên Pull Request kèm mức độ và gợi ý sửa; nhiều reviewer chuyên biệt; học từ phản hồi của team. | NNQuí |
| **3** | Helpdesk Agent | Chăm sóc khách hàng: trả lời có trích dẫn, tra cứu đơn hàng, tạo ticket, chuyển cho nhân viên thật khi cần. | QCKAn |
| **4** | GEO content writer Agent | Nghiên cứu nguồn, viết bài theo giọng thương hiệu, kiểm chứng số liệu, đo mức độ được AI trích dẫn. | DNPNam |
| **5** | Interview Agent | Lên kịch bản từ JD và CV, phỏng vấn nhiều lượt, chấm theo rubric có dẫn chứng; người ra quyết định cuối. | DNPNam |
| **6** | IELTS Learning Agent | Chấm Writing theo band descriptors, thi thử Speaking, sinh bài Reading/Listening, lập kế hoạch học theo điểm yếu. | NTHAnh |
| **7** | Business Ops Agent | Như Hermes, dựng sẵn đội agent phòng ban (Sales, Marketing, HR, Kế toán, CSKH, Vận hành) có agent điều phối. | NHNghĩa |
| **8** | Tour Guide Agent | Lên lịch trình bằng tool thời tiết, bản đồ; thuyết minh điểm đến Việt Nam song ngữ, đổi lịch khi có sự cố. | NTHAnh |
| **9** | Analytics Agent | Hỏi bằng câu tự nhiên, agent viết và chạy SQL, vẽ biểu đồ, tìm nguyên nhân biến động; chỉ có quyền đọc dữ liệu. | QCKAn |
| **10** | AI Training Agent | Cùng người dùng dựng scenario, đóng vai các nhân vật để người học luyện kỹ năng, rồi chấm và cho feedback. | NNQuí |