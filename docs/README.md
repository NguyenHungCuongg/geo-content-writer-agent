# Tài liệu dự án

Mục lục cho thành viên nhóm. Agent (Claude Code, Codex...) đọc [../AGENTS.md](../AGENTS.md) trước.

## `guide/`: tài liệu đồ án của giảng viên

| File | Nội dung | Đọc khi |
|---|---|---|
| [final-project-information.md](guide/final-project-information.md) | Lộ trình 3 phase, hình thức trình bày, cách tính điểm, danh sách 10 đề tài | Lần đầu vào dự án |
| [rubic-final-project.md](guide/rubic-final-project.md) | Rubric chi tiết: 8 mảng kiến thức K1-K8, yêu cầu nền HR-01..07, mức Giỏi/Khá/TB/Yếu của từng tiêu chí, điểm trừ, vấn đáp | Chọn UC, thiết kế harness, trước mỗi lần nộp |
| [geo-content-writer-agent-requirement.md](guide/geo-content-writer-agent-requirement.md) | Đặc tả đề tài 04: luật cấm, môi trường (brand kit, mini-web, bộ eval, WordPress), 11 UC chi tiết, tool và quyền, case tấn công, sản phẩm nộp | Trước khi làm UC mình sở hữu |

Khi rubric và đặc tả đề tài khác nhau, **rubric được ưu tiên**.

## Tóm tắt nhanh

**Điểm (đồ án = 50% điểm môn, thang 10):**

- Agent tối đa 7,5: mỗi UC 1,5 điểm = U1 chức năng 0,5 + U2 thiết kế harness 0,5 + U3 kiểm chứng (eval, trace) 0,5. Làm 6-7 UC để dự phòng; tổng chặn trần 7,5.
- Phần mềm tối đa 2,5: sáng tạo 0,5, độ phức tạp 0,75, độ hoàn thiện 0,75, khối lượng 0,5. Khung chat bọc LLM không được tính.
- Tập UC nộp phải phủ đủ K1-K8; thiếu mỗi mảng trừ 0,5.
- Điểm cá nhân = điểm nhóm × hệ số vấn đáp (0-1,0). Mỗi người phải giải thích được UC mình sở hữu và phần chung.

**Hạn nộp:** Phase 1 ngày 27/10/2026, Phase 2 ngày 10/11/2026, Phase 3 ngày 06/12/2026. Chi tiết từng phase xem [AGENTS.md](../AGENTS.md#phase-hiện-tại).

**11 UC và mảng K** (đặc tả mục 3.1):

| UC | Tên | K |
|---|---|---|
| 01 | Phân tích thương hiệu, sinh tập prompt | K1 |
| 02 | Nghiên cứu nguồn, kho tri thức có trích dẫn | K2, K3, K8 |
| 03 | Dàn ý GEO, viết bài theo giọng thương hiệu | K1, K2 |
| 04 | Fact-checker agent | K3, K6, K7 |
| 05 | Editor agent chấm checklist SEO-GEO | K6, K7 |
| 06 | Sinh và kiểm tra JSON-LD | K1, K7 |
| 07 | Đo AI visibility trước/sau | K2, K4, K7 |
| 08 | Làm mới bài cũ | K3, K5 |
| 09 | Lịch nội dung + bộ nhớ thương hiệu dài hạn | K4, K5 |
| 10 | Duyệt và xuất bản WordPress | K5, K8 |
| 11 | MCP server `geo-tools` | K6, K8 |

Ví dụ tổ hợp 5 UC phủ đủ K1-K8: 02 + 03 + 04 + 07 + 09.

## `ref/`: slide môn học

| Buổi | Chủ đề | Mảng K |
|---|---|---|
| [1](ref/Buoi%201%20-%20%20Gioi%20Thieu%20Mon%20Hoc%20va%20Tong%20Quan%20Agentic%20AI.md) | Tổng quan LLM và Agentic AI; chatbot/RAG/workflow/agent; **12 lớp harness** | nền cho HR-03 |
| [2](ref/Buoi%202.%20C%C3%A1c%20nguy%C3%AAn%20l%C3%BD%20c%C6%A1%20b%E1%BA%A3n%20c%E1%BB%A7a%20LLM-powered%20app.md) | Token, context window, prompt/context engineering, structured output (Pydantic), function calling | K1 |
| [3](ref/Buoi%203.%20Agent%20Fundamentals.md) | Vòng lặp agent, ReAct, plan-then-execute, reflection, 5 điều kiện dừng, debugging | K1 |
| [4](ref/Buoi%204%20-%20From%20Prompt%20Engineering%20to%20Reusable%20Skills.md) | Agent skill: cấu trúc thư mục, `SKILL.md`, trigger, workflow, verification | K2 |
| 5 | Tool use (chưa có file) | K2 |
| [6](ref/Buoi%206%20-%20RAG%20Knowledge%20Harness.md) | RAG: ingestion, chunking, metadata, embedding, vector DB, hybrid search, RRF, reranking | K3 |
| [7](ref/Buoi%207%20-%20Memory,%20context%20engineering,%20prompt%20caching.md) | Memory, state, compaction, structured checkpoint, prompt caching | K4 |
| 8-11 | Workflow/HITL (K5), eval (K7), multi-agent/MCP (K6), security (K8): chưa có file | K5-K8 |

Khi có slide mới, thêm file vào `ref/` theo tên `Buoi N - <chủ đề>.md` và cập nhật bảng trên.
