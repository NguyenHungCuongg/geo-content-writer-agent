# Bảng phân công

Bắt buộc theo HR-07. Mỗi SV sở hữu ít nhất 1 UC và chịu trách nhiệm UC đó từ đầu đến cuối: code, eval case, trace, trả lời vấn đáp.

## Use case

| UC | Tên | K | Owner |
|---|---|---|---|
| UC-01 | Phân tích thương hiệu, sinh tập prompt | K1 | |
| UC-02 | Nghiên cứu nguồn, kho tri thức có trích dẫn | K2, K3, K8 | |
| UC-03 | Dàn ý GEO, viết bài theo giọng thương hiệu | K1, K2 | |
| UC-04 | Fact-checker agent | K3, K6, K7 | |
| UC-09 | Lịch nội dung + bộ nhớ thương hiệu dài hạn | K4, K5 | |

Độ phủ: đủ K1-K8 ([D-07](decisions.md)).

**Dự phòng** (chỉ nộp khi đủ eval, trace, màn hình, video):

| UC | Tên | K | Owner |
|---|---|---|---|
| UC-07 | Đo AI visibility trước/sau | K2, K4, K7 | |
| UC-10 | Duyệt và xuất bản WordPress | K5, K8 | |

## Phần chung

| Phần | Người phụ trách |
|---|---|
| Harness chung (agent loop, tool, trace) | |
| Phần mềm (backend FastAPI) | |
| Phần mềm (frontend React) | |
| Eval runner, CI | |
| Báo cáo, video | |
