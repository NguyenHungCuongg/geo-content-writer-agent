# GEO Content Writer Agent

Đồ án cuối kỳ SE373: agent viết bài blog tiếng Việt tối ưu GEO cho một thương hiệu hư cấu, có kho tri thức trích dẫn nguồn, fact-checker, editor, điểm duyệt của người và tập eval.

- Thành viên mới: đọc [docs/README.md](docs/README.md).
- Coding agent: đọc [AGENTS.md](AGENTS.md).

## Chạy app

Yêu cầu: Python ≥ 3.11, Node 24.

1. Cài đặt (ở gốc repo):

   ```bash
   pip install -e ".[dev]"
   cp .env.example .env   # rồi điền GEMINI_API_KEY và GEMINI_MODEL
   ```

2. Backend, chạy **từ gốc repo** (skill trong `skills/` được đọc theo đường dẫn trong repo):

   ```bash
   uvicorn app.backend.main:app --reload
   ```

3. Frontend, ở terminal khác:

   ```bash
   cd app/frontend
   npm ci
   npm run dev
   ```

   Mở http://localhost:5173, dán brief (ví dụ nội dung `data/brand/brief_sample.md`), nhập chủ đề rồi bấm **Chạy UC-01**. Vite chuyển các request `/runs` sang backend ở cổng 8000.

Chạy UC-01 không cần app:

```bash
python -m agent.uc01 --brief data/brand/brief_sample.md --topic "sơn chống nóng mái tôn"
```

## Chạy eval

```bash
python -m evals.run --all            # live: gọi Gemini thật, cần đủ 3 biến GEMINI_* trong .env
python -m evals.run --all --offline  # LLM giả, không tốn quota: chỉ kiểm harness, không đo agent
```

Kết quả từng case và tổng pass/fail ghi vào `evals/results/<timestamp>.json`; lệnh trả mã 1 nếu có case trượt. Case nằm ở `evals/cases/uc01/`. Bản live tốn vài trăm lời gọi embedding, mà free tier chỉ cho 1.000 câu/ngày mỗi project, nên mỗi ngày chỉ chạy được 1-2 lần.
