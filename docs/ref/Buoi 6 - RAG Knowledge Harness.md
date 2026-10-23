# Buổi 06 – RAG cho hệ thống phần mềm: Knowledge Harness trong Agentic AI

*SE373 · Kỹ thuật xây dựng hệ thống Agentic AI*

**Mục tiêu cốt lõi:** xây dựng pipeline RAG có trích dẫn kiểm chứng được và đo được chất lượng bằng số liệu.

## Nội dung buổi học

1. RAG trong kiến trúc harness
2. Ingestion, chunking và metadata
3. Embedding và vector database
4. Retrieval, hybrid search và reranking
5. Grounding, citation và đánh giá

---

## Phần 01 – RAG trong kiến trúc Harness

### Khái niệm RAG

> **RAG (Retrieval-Augmented Generation)** là mẫu kiến trúc sinh câu trả lời từ ngữ cảnh truy xuất ở kho dữ liệu ngoài.

- **Vị trí:** lớp harness nằm giữa LLM và kho tri thức.
- **Trách nhiệm:** quyết định chunk nào được đưa vào context.

Luồng: User Query → Retrieval Layer (harness) → Relevant Chunks (từ Knowledge Store, dữ liệu ngoài) → Context Injection / Prompt Assembly (harness) → Large Language Model → Grounded Answer.

### Ba cơ chế nạp tri thức

1. **Fine-tuning:** nạp vào trọng số model.
2. **Context stuffing:** dán toàn bộ tài liệu vào prompt.
3. **Retrieval (RAG):** truy xuất chunk liên quan theo từng truy vấn.

RAG đáp ứng đồng thời ba tiêu chí: **cập nhật tức thì**, **có thể trích dẫn nguồn**, và **cho phép xoá/thu hồi dữ liệu**.

### Kiến trúc RAG hai pha

**Pha nạp (offline indexing):**
Repo / Docs / Issues → [01] Document Loader → [02] Data Cleaning → [03] Chunking & Metadata → [04] Embedding Generation → [05] Vector DB / Index

**Pha truy vấn (online querying):**
User Query → [06] Query Transformation → [07] Query Embedding → [08] Hybrid Retrieval → [09] CrossEncoder Rerank → [10] Prompt Assembly → [11] LLM Generation → [12] Citation Verification

> Hai pha bắt buộc dùng chung đúng một embedding model.

### Thách thức khi nhồi context

- **Chi phí token:** tăng tuyến tính theo số truy vấn.
- **Độ chính xác khai thác thông tin:**
  - *Lost in the middle:* thông tin ở giữa prompt bị bỏ sót (đầu và cuối prompt có độ chính xác cao, vùng giữa suy giảm mạnh).
  - *Context rot:* context càng dài, suy luận càng kém.

> Dù context dài đến đâu, vẫn cần RAG để chọn đúng phần cần đọc.

### Năm loại tài liệu kỹ thuật và chiến lược phân đoạn

| Loại tài liệu | Chiến lược phân đoạn |
|---|---|
| README | Cắt theo heading, giữ `heading_path` |
| API Docs | Một endpoint = một chunk |
| Source code | Cắt theo AST, kèm chữ ký hàm |
| Spec / ADR | Theo section, lưu status và date |
| Issue / PR | Giữ trọn issue, kèm trạng thái |

> Cắt theo độ dài cố định làm hỏng ngữ nghĩa của cả 5 loại.

### Tổng kết phần 1

1. RAG là lớp harness retrieval: quyết định model được đọc tài liệu nào.
2. Một embedding model cho cả hai pha: ingest và search dùng cùng một model.
3. Tài liệu phần mềm có cấu trúc: mỗi loại một chiến lược phân đoạn.

---

## Phần 02 – Ingestion, chunking và metadata

### Pipeline ingestion

Git Repo / Docs / Issues → [01] Loader (trích xuất thô) → [02] Clean (lọc nhiễu kỹ thuật) → [03] Split (phân đoạn cấu trúc) → [04] Metadata (định danh & phiên bản) → [05] Vector Store.

> **Câu hỏi tiên quyết:** đơn vị nào là một tài liệu hoàn chỉnh? Ví dụ: code là từng file; issue tracker là từng ticket.

### Tiền xử lý dữ liệu kỹ thuật

1. **Loại bỏ nhiễu:** badge, TOC, navigation, footer.
2. **Bảo toàn code block:** không cắt ngang, không loại bỏ.
3. **Giữ header bảng:** bảng mất header thành vô nghĩa.
4. **Mô tả sơ đồ:** vision model chuyển hình thành text.

> Tiền xử lý phải **deterministic** (cùng đầu vào, luôn cùng kết quả) và có log.

### Chunk và overlap

- **Chunk:** phân đoạn đủ nhỏ để truy xuất chính xác, đủ lớn để mang trọn ngữ nghĩa.
- **Chunking strategy:** quy tắc xác định ranh giới chunk.
- **Overlap:** vùng gối đầu giữa hai chunk liền kề.

### Ba họ chiến lược chunking

1. **Fixed-size:** đều đặn, nhưng hay cắt ngang thân hàm.
2. **Structure-based:** theo heading, nhưng kích thước chênh lệch.
3. **Semantic:** ranh giới tự nhiên, nhưng tốn chi phí nạp.

> Với tài liệu phần mềm, ưu tiên kết hợp: cắt theo heading trước; đoạn nào còn dài thì cắt tiếp theo kích thước.

### Rủi ro khi cắt code theo ký tự

```python
# Chunk 1: Lưu trong index
class SessionManager:
    def refresh_token(self, sid: str) -> Token:
        state = self._load(sid)
        # ... logic cắt ngang tại đây ...

# Chunk 2: Mất hoàn toàn ngữ cảnh
        if token.expired:
            raise AuthTokenExpiredError()
        self._state = 'active'
        return token
```

Chunk bắt đầu giữa thân hàm khiến embedding mất phần lớn ngữ nghĩa.

### Cắt code theo cú pháp (syntax-aware)

```python
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

py_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.PYTHON,
    chunk_size=2000,
    chunk_overlap=200
)
chunks = py_splitter.create_documents(
    [code_content],
    metadatas=[{"path": "src/session.py", "lang": "python"}]
)
```

Ưu tiên giữ ranh giới class và hàm trước khi tách thân hàm.

### Chunk = text + metadata

> Metadata là **tọa độ** của chunk: file nào, phần nào, phiên bản nào, còn hiệu lực không.

Metadata cho phép: trích dẫn chính xác dòng/file; kiểm chứng nguồn gốc tự động; thu hồi và xoá bỏ (idempotent); lọc phân cấp theo version và status.

> Không có metadata thì không trích dẫn được file, dòng, phiên bản.

### Metadata schema cho codebase

| Thuộc tính | Ví dụ |
|---|---|
| `source_type` | `api_doc`, `code`, `adr`, `issue` |
| `repo` + `path` | `payment-service`, `src/auth.py` |
| `version` / `commit` | `v2.4.0`, `a3f91c2` |
| `line_start`, `line_end` | 118, 173 |
| `heading_path` | API > Sessions > POST /v2 |
| `symbol` | `SessionManager.refresh_token` |
| `status` | `active`, `superseded`, `wontfix` |
| `doc_id`, `chunk_id` | `sha1_hash:idx` |

### Contextual Retrieval

- Gắn 50–100 token mô tả ngữ cảnh vào đầu chunk trước khi embedding.
- Ví dụ: "Tài liệu `docs/api.md`, mục Deprecated v1 của service thanh toán, mô tả endpoint `POST /v1/sessions`, đã được thay bởi API v2."
- Chi phí một lần ở indexing giúp **giảm 49% lỗi truy xuất** (67% nếu thêm reranking).
- Nguồn: Anthropic (2024), *Introducing Contextual Retrieval*.

### Tổng kết phần 2

1. Tiền xử lý deterministic.
2. Cách cắt phải được đo: chọn bằng Recall@k trên dữ liệu thật.
3. Chunk = text + metadata. Không có metadata thì không trích dẫn được.
4. Giữ code block, header bảng, và có log.

---

## Phần 03 – Embedding và vector database

### Khái niệm embedding

> **Embedding** là vector số thực ánh xạ ngữ nghĩa văn bản vào không gian hình học.

- **Cosine similarity:** đo độ gần giữa hai vector.
- **ANN (Approximate Nearest Neighbor):** tìm láng giềng gần đúng, đổi chính xác lấy tốc độ.

Ví dụ: "refresh access token" và "làm mới token" cho vector gần như giống nhau.

### Bắt ngữ nghĩa, mất ký tự

- **Không gian văn xuôi (rất hiệu quả):** "làm mới token", "refresh access token", "xoay vòng khoá xác thực" → vector sát nhau.
- **Định danh kỹ thuật (bất khả thi):** `AuthTokenExpiredError`, `AuthTokenInvalidError`, `SessionExpiredError` → vector vẫn gần như trùng nhau.

> Embedding mạnh với văn xuôi nhưng yếu khi phân biệt các mã định danh gần giống nhau.

### Khoá cứng embedding model (lock-in)

- Khác số chiều: báo lỗi ngay, dễ sửa.
- Cùng số chiều, khác model: **không báo lỗi, kết quả gần như ngẫu nhiên.**

```python
assert store.metadata["embed_model"] == "text-embedding-3-small", \
    "FATAL: Vector store được index bằng model khác với query model"
```

> Đổi embedding model thì phải ingest lại (re-embed) toàn bộ dữ liệu.

### So sánh vector database cho đồ án

| Tiêu chí | Chroma | FAISS | Qdrant | pgvector |
|---|---|---|---|---|
| Bản chất | Vector DB nhúng | Thư viện ANN | Vector DB chuyên dụng | Extension PostgreSQL |
| Lưu metadata | Có | Không | Có | Có |
| Metadata filtering | Có (`where`) | Không | Payload filter | SQL `WHERE` |
| Setup | `pip install` | Thấp | Docker | Có Postgres là đủ |
| Phù hợp | Đồ án | Pipeline nhúng | Scale lớn | Hệ thống có sẵn Postgres |

- Môn học dùng Chroma; lấy dư k = 20–50 rồi rerank còn 3–5.
- Nguồn: tài liệu kỹ thuật trychroma.com, qdrant.tech, pgvector.

### Cài đặt upsert idempotent

```python
import hashlib
from langchain_chroma import Chroma

def upsert_file_idempotent(store: Chroma, path: str, chunks: list) -> None:
    doc_id = hashlib.sha1(path.encode()).hexdigest()[:12]

    # BƯỚC 1: Xoá toàn bộ chunk cũ của tài liệu
    store.delete(where={"doc_id": doc_id})

    # BƯỚC 2: Sinh chunk_id tất định
    ids = [f"{doc_id}:{i}" for i in range(len(chunks))]
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({"doc_id": doc_id, "chunk_id": ids[i], "path": path})

    # BƯỚC 3: Ghi chunk mới
    store.add_documents(chunks, ids=ids)
```

> Xoá chunk cũ trước khi ghi: chạy lại bao nhiêu lần, index vẫn đúng.

### Demo A: ingest và tìm kiếm tài liệu môn học

| Bước | Thao tác | Quan sát |
|---|---|---|
| 01 Ingest | Đọc 4 file Markdown, cắt theo heading | 24 chunk, có path, heading; `collection.count() = 24` |
| 02 Embedding | Gemini tạo vector, lưu vào Chroma | — |
| 03 Tìm kiếm | "Tiêu chí chấm A3?" | Top-3 có rubric A3 |
| 04 Câu định danh | "CLO G3.3 nói gì?" | G3.3 đứng hạng 6 (bị tụt hạng) |

---

## Phần 04 – Retrieval, hybrid search và reranking

### Phân tích ca thất bại Demo A (CLO G3.3)

Truy vấn: "CLO G3.3 nói gì?" với dense vector search:
- Hạng 1: bảng thành phần đánh giá · cosine 0,715
- Hạng 2: chunk CLO G1.1 · cosine 0,377
- Hạng 3: chunk CLO G4.2 · cosine 0,321
- …
- Hạng 6: chunk CLO G3.3 (**đáp án đúng**) · bị tụt hạng

Với embedding model, "G3.3" chỉ là chuỗi ký tự vô nghĩa. Mọi chunk CLO có ngữ cảnh giống nhau nên vector sát nhau. Với dense retrieval, các mã định danh gần như trùng toạ độ.

### Dense retrieval và sparse retrieval

| | Dense (vector embeddings) | Sparse (BM25 / keyword) |
|---|---|---|
| Khớp theo | Không gian ngữ nghĩa | Chuỗi ký tự chính xác |
| Điểm mạnh | Hiểu từ đồng nghĩa, diễn đạt khác; đa ngôn ngữ | Bắt trọn mã lỗi, endpoint, định danh; logic Boolean; dễ giải thích |

> BM25 là hàm chấm điểm theo tần suất từ trên inverted index, chuẩn công nghiệp cho tìm kiếm từ khoá.

### Kiến trúc hybrid search

Hybrid search chạy song song dense và sparse, rồi hợp nhất hai bảng xếp hạng:

User Query → Sparse search (BM25, khớp chính xác chuỗi) và Dense search (vector, khớp ngữ nghĩa) → bảng xếp hạng BM25 + bảng xếp hạng Vector → **hợp nhất bằng Reciprocal Rank Fusion** → Top-k chunks.

> Bài toán cốt lõi là hợp nhất hai thang điểm khác nhau.

### Vì sao không cộng thẳng điểm số?

| Chunk | A | B |
|---|---|---|
| Điểm BM25 | 14,2 | 3,1 |
| Điểm cosine | 0,79 | 0,84 |

- BM25 không có cận trên: có thể là 3 hay 30.
- Cosine: các kết quả đầu bảng chụm sát nhau.
- Cộng thẳng: BM25 lấn át, vector mất tiếng nói.

> Hai thang điểm khác nhau thì không cộng thẳng được.

### Reciprocal Rank Fusion (RRF)

- Bỏ điểm số, chỉ dùng thứ hạng của chunk.
- Mỗi danh sách cho chunk `1 / (k + hạng)`.
- Cộng lại: chunk có mặt ở nhiều danh sách sẽ được cộng nhiều lần.

$$\text{RRF}(d) = \sum_{m} \frac{1}{k + \text{rank}_m(d)}$$

- Σ: cộng qua mọi danh sách (vector, BM25).
- rank_m(d): hạng của chunk d trong danh sách m.

> Hợp nhất theo thứ hạng, không theo điểm số.

### Hằng số k = 60

| Hạng | k = 0 | k = 60 |
|---|---|---|
| 1 | 1/1 = 1,000 | 1/61 ≈ 0,0164 |
| 2 | 1/2 = 0,500 | 1/62 ≈ 0,0161 |
| 3 | 1/3 = 0,333 | 1/63 ≈ 0,0159 |

- k = 0: đứng đầu một danh sách là thắng.
- k = 60: chunk được cả hai danh sách đồng ý sẽ thắng. k lớn san phẳng chênh lệch giữa các hạng đầu.
- Nguồn: Cormack, Clarke & Büttcher (SIGIR 2009); Azure AI Search dùng k = 60.

### Cài đặt RRF bằng Python

```python
def rrf(rank_lists, k=60, top_n=5):
    scores = {}
    for ranked in rank_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)[:top_n]

vec_hits = ["c_G3_1", "c_G2_2", "c_G3_3", "c_G3_2"]   # G3.3 hạng 3
bm25_hits = ["c_G3_3", "c_appendix"]                   # G3.3 hạng 1

rrf([vec_hits, bm25_hits], top_n=3)  # ['c_G3_3', 'c_G3_1', 'c_G2_2']
```

Sáu dòng code đẩy chunk đúng `c_G3_3` lên hạng 1.

### Vì sao cần reranking?

| Bước | Retrieval | Hybrid search (RRF) | Reranking |
|---|---|---|---|
| Số chunk | 10.000 | 100 | 40 → 3–5 |
| Cách làm | Toàn bộ chunk đã ingest | Dense và BM25 mỗi bên lấy 50; hợp nhất, bỏ trùng | Đọc kỹ từng ứng viên, giữ chunk tốt nhất |

- Retrieval: quét nhanh cả kho, lấy dư ứng viên.
- Vấn đề: 40 ứng viên vẫn nhiều; chunk đúng chưa chắc đứng đầu.
- Reranking: đọc kỹ từng ứng viên, xếp lại theo mức liên quan.

> Retrieval lo tìm đủ; reranking lo xếp đúng.

### Cross-encoder: đọc câu hỏi và chunk cùng lúc

Đầu vào: `[CLS] CLO G3.3 nói gì? [SEP] CLO G3.3: Xây dựng được pipeline RAG ... [SEP]` → Transformer (cross-attention) → relevance score, ví dụ 0,94.

- Mỗi từ của câu hỏi đối chiếu mọi từ trong chunk.
- Đầu ra: một điểm liên quan cho từng cặp.

> Cross-encoder là model chấm điểm cặp (câu hỏi, chunk); không tạo vector.

```python
from sentence_transformers import CrossEncoder

class CrossEncoderReranker:
    def __init__(self, model_name="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"):
        self._model = CrossEncoder(model_name)

    def rerank(self, query, hits, top_n=5):
        scores = self._model.predict([(query, h["text"]) for h in hits])
        scored = [{**h, "rerank": float(s)} for h, s in zip(hits, scores)]
        return sorted(scored, key=lambda h: h["rerank"], reverse=True)[:top_n]
```

- Tiếng Việt: dùng model đa ngôn ngữ như `mmarco-mMiniLMv2` hoặc `bge-reranker-v2-m3`.
- Reranker chỉ là hàm predict trên danh sách cặp (câu hỏi, chunk).

### Kiến trúc retrieval cascade

Kho dữ liệu: 10.000 chunk.
1. **Truy xuất rẻ và lấy dư:** BM25 (top 50) + vector ANN (top 50).
2. **Hợp nhất thứ hạng:** Reciprocal Rank Fusion → khoảng 40 chunk.
3. **Reranking chính xác cao:** cross-encoder chấm điểm lại 40 chunk.
4. **Tinh lọc context:** 3–5 chunk xuất sắc nhất đưa vào prompt.

> Lấy nhiều ứng viên bằng cách rẻ, rồi lọc lại bằng reranker.

### Các kỹ thuật query transformation

| Kỹ thuật | Cơ chế |
|---|---|
| Query rewriting | Viết lại câu hỏi rõ nghĩa hơn |
| Multi-query | Sinh 3–5 biến thể, tìm song song |
| Step-back | Hỏi thêm ở mức khái niệm rộng |
| HyDE | LLM viết thử câu trả lời, dùng nó để tìm |
| Decomposition | Tách câu hỏi phức thành chuỗi câu đơn |

Nguồn: Infante (2026) ch.9; Gao et al. (HyDE, 2022); Ma et al. (2023).

### Demo B: hybrid search và reranking sửa ca G3.3

1. Dense (Gemini embedding).
2. BM25 (khớp từ khoá).
3. Hybrid search (RRF, k = 60).
4. Rerank 20 → 5 (Gemini chấm điểm).
5. Trả lời bám nguồn.

**Điều cần nhìn:** hạng của G3.3; khớp đúng chữ "g3.3"; hợp nhất hai bảng đưa G3.3 lên đầu; mỗi ý có trích dẫn `[S1]`.

> Hybrid search tìm thấy; reranking đưa lên đầu.

### Tổng kết phần 4

1. Hybrid search là chuẩn.
2. RRF hợp nhất theo thứ hạng.
3. Lấy dư rồi tinh lọc.
- Dense cho ngữ nghĩa, BM25 cho từ khoá chính xác. `1/(k + rank)`, k = 60.
- Reranker chỉ sắp lại; chunk chưa lấy về thì không cứu được.

---

## Phần 05 – Grounding, citation và đo lường

### Khái niệm grounding

> **Grounding** ràng buộc câu trả lời chỉ hình thành từ dữ kiện trong context được cung cấp.

- LLM không tự bám nguồn; phải thiết kế qua prompt và harness.
- **Escape hatch:** cho phép model từ chối khi không đủ căn cứ.

Ví dụ: hỏi "Đền Hera I có bao nhiêu cột?"
- Không grounding → "Có 94 cột" (sai).
- Có grounding → "Tài liệu không đề cập số lượng cột."

### Năm quy tắc bám nguồn (prompt design)

1. Không suy diễn ngoài tài liệu được cung cấp.
2. Mọi khẳng định kết thúc bằng trích dẫn `[ID]`.
3. Không đủ căn cứ: "Không đủ căn cứ trong tài liệu."
4. Hai nguồn mâu thuẫn: nêu cả hai, kèm version và status.
5. Tài liệu deprecated chỉ dùng khi hỏi về lịch sử.

> Quy tắc 4 và 5 chỉ thực thi được khi metadata đã được gắn từ pha nạp.

### Citation

> **Citation** (trích dẫn nguồn) là phần đánh dấu cho biết mỗi ý trong câu trả lời lấy từ tài liệu nào.

- **Tăng độ tin cậy:** người dùng tự kiểm chứng, giảm ảo giác.
- **Minh bạch:** buộc LLM bám tài liệu, không dựa vào trí nhớ.
- **Dẫn nguồn:** nối câu trả lời với văn bản gốc.

Citation cho biết câu trả lời đến từ đâu.

### Citation hoạt động thế nào?

1. **Truy xuất:** tìm các chunk liên quan. Ví dụ: `[S1] src/session.py`, `[S2] docs/api.md` ("Hàm ném AuthTokenExpiredError khi token hết hạn").
2. **Sinh văn bản:** LLM trả lời dựa trên chunk.
3. **Gắn trích dẫn:** gắn mã nguồn vào từng ý: "... khi token hết hạn [S1]."

> Rủi ro: LLM có thể bịa mã nguồn hoặc gán sai nguồn. **Citation phải kiểm chứng bằng chương trình, không tin mặc định.**

### Bốn retrieval failure modes

| Mode | Dấu hiệu | Đo bằng | Khắc phục |
|---|---|---|---|
| 01 · Miss | Chunk đúng không có trong top-k | Recall@k | BM25, tăng k, Contextual Retrieval |
| 02 · Wrong chunk | Top-k nhiễu hoặc trùng lặp | Precision@k | Lọc metadata, Parent-Child |
| 03 · Nguồn mâu thuẫn | Bản cũ và mới cùng lọt top-k | Faithfulness, Abstention | Upsert idempotent, status bản |
| 04 · Ảo giác dù có nguồn | Đúng chunk, vẫn nói sai | Escape hatch, entailment | — |

Nguồn: Barnett et al. (CAIN 2024), *Seven Failure Points When Engineering a RAG System*.

### Nghiên cứu: cạm bẫy ngữ cảnh không đủ

Ngữ cảnh không đủ là context thiếu dữ kiện, mơ hồ hoặc mâu thuẫn. Tỉ lệ trả lời sai của Gemma (Google, ICLR 2025):
- Không có ngữ cảnh: 10,2%
- Ngữ cảnh không đủ: 66,1% (gấp khoảng 6,5 lần)

> Ngữ cảnh nửa vời nguy hiểm hơn không có ngữ cảnh.

Nguồn: Joren et al. (2025), *The Role of Sufficient Context*, ICLR.

### Thiết kế golden dataset

- **Golden dataset:** 20–30 câu hỏi do người gán sẵn vị trí đáp án (chunk, dòng).
- Cơ cấu chuẩn:
  - 1/3 khái niệm: câu hỏi lý thuyết thông thường.
  - 1/3 định danh: tên lỗi, đoạn code, endpoint API.
  - 1/3 câu bẫy: phiên bản cũ, câu hỏi phủ định.
  - **Bắt buộc 3–5 câu không có đáp án trong kho.**

> Thiếu câu hỏi không có đáp án thì không đo được lỗi bịa câu trả lời (failure mode 4).

### Bộ chỉ số đánh giá

| Chỉ số | Câu hỏi nó trả lời |
|---|---|
| Recall@k | Có tìm thấy chunk đúng không? |
| Precision@k | Lấy về có thừa chunk không? |
| MRR | Chunk đúng đứng hạng mấy? |
| Faithfulness | Câu trả lời có đúng tài liệu không? |
| Citation existence | Mã trích dẫn có thật không? |
| Abstention rate | Không có đáp án, có dám nói "không biết" không? |

Ba chỉ số đầu chấm bước tìm; ba chỉ số sau chấm câu trả lời.

### Ví dụ đo bước tìm tài liệu

Câu hỏi: "Endpoint nào dùng để làm mới token?"

| Hạng | Chunk lấy về | Kết quả |
|---|---|---|
| 1 | `docs/api.md` · mục Deprecated v1 | Sai |
| 2 | `docs/api.md` · `POST /v2/sessions/refresh` | Đúng |
| 3 | `src/payments/session.py` · `refresh_token` | Hữu ích |
| 4 | `docs/adr/0001-session-tokens-v1.md` | Sai |
| 5 | `README.md` | Sai |

- Recall@5 = 1: chunk đúng có trong top-5.
- Precision@5 = 2/5 = 0,4: chỉ 2 trên 5 chunk hữu ích.
- MRR = 1/2 = 0,5: chunk đúng đầu tiên ở hạng 2.

> Recall@k thấp thì mọi kỹ thuật phía sau đều vô ích.

### Ví dụ đo câu trả lời

Câu trả lời mẫu (prompt chỉ đưa vào S1, S2):
1. Client gọi `POST /v2/sessions/refresh` [S1] — đúng tài liệu
2. Request cần `session_id`, `refresh_token` [S1] — đúng tài liệu
3. Hàm dùng lock nội bộ, thread-safe [S3] — **bịa**: S3 không có trong prompt và tài liệu không nói

- **Faithfulness = 2/3:** ý thứ ba tài liệu không hề nói.
- **Citation existence: lỗi**, vì [S3] không có trong prompt.
- **Abstention rate = 4/5:** 5 câu không có đáp án, từ chối đúng 4.

> Citation existence bắt buộc 100%: một mã bịa là lỗi.

### Faithfulness qua ví dụ RAGAS

> Faithfulness là tỷ lệ mệnh đề trong câu trả lời được context chứng thực (0–1).

- Ngữ cảnh: "Albert Einstein sinh ngày 14/3/1879 tại Đức."
- Trả lời: "Einstein sinh tại Đức [S1] vào ngày 20/3/1879 [S1]."
  - "Sinh tại Đức" → được chứng thực.
  - "Sinh ngày 20/3" → mâu thuẫn ngữ cảnh.
- Faithfulness = 1 / 2 = 0,5.

### Bảng so sánh cấu hình cho đồ án

| Cấu hình | Mô tả |
|---|---|
| A · Baseline | Vector, chunk 500 |
| B · Structured | Heading + metadata |
| C · Hybrid | B + BM25, RRF |
| D · Cascade | C + cross-encoder |

Chỉ số đo: Recall@5, Recall@20, Faithfulness, Citation accuracy, Abstention, Latency p50.

> Mỗi cấu hình chỉ đổi một yếu tố, rồi so bằng số liệu.

### Just-in-time retrieval và agent

- **RAG truyền thống:** một lượt cố định.
- **Just-in-time:** chỉ giữ tên file; cần thì mới đọc nội dung.
- **Agentic retrieval:** agent tự chọn tool và lặp đến khi đủ căn cứ.

Luồng: Agent planner → tool `search_codebase` → trả về kết quả có `chunk_id` → đủ căn cứ thì đưa ra grounded final answer; chưa đủ thì lặp lại.

### Đóng gói retrieval thành tool cho agent

```python
from langchain_core.tools import tool
from langchain.agents import create_agent

@tool
def search_codebase(query: str, source_type: str = "any", k: int = 5) -> str:
    """Tìm trong tài liệu kỹ thuật và mã nguồn repo payment-service."""
    filters = None if source_type == "any" else {"source_type": source_type}
    results = store.similarity_search(query, k=k, filter=filters)
    return "\n\n".join(
        f"[{d.metadata['chunk_id']}] {d.metadata['path']}\n{d.page_content}"
        for d in results
    )

agent = create_agent(model="claude-sonnet-4-5", tools=[search_codebase])
```

> Retrieval chuyển từ bước tĩnh thành năng lực hành động của agent.

### Tổng kết phần 5

1. Grounding: chỉ trả lời từ tài liệu; thiếu căn cứ thì từ chối.
2. Citation: mỗi ý gắn nguồn, kiểm chứng được bằng chương trình.
3. Bốn failure mode, đo bằng số: Recall, Precision, Faithfulness, Abstention.

### Bài tập đồ án: thêm RAG vào đồ án cuối kỳ

Triển khai và đánh giá RAG trên một branch riêng (ví dụ `feature/rag`) của đồ án nhóm:
- **Ingest:** nạp tài liệu của đồ án, gắn đủ metadata.
- **Truy vấn:** hybrid search và reranking, có trích dẫn.
- **Golden dataset:** 20 câu, có 3–5 câu không có đáp án.
- **Đo:** điền bảng so sánh cấu hình, tối thiểu 2 cấu hình.
- **Báo cáo:** bảng số liệu và một ca thất bại.
