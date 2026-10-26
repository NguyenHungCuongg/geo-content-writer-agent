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
