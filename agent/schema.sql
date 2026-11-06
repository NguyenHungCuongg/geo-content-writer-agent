-- agent.db.migrate chạy file này trong schema đích (search_path = <schema>, public).
-- Mọi lệnh phải chạy lại được (IF NOT EXISTS) và không ghi tên schema.
-- Bảng của mỗi UC do owner UC đó thêm vào cuối file (Task 4: chunks, embedding_cache).

-- Extension luôn ở public: DROP SCHEMA ... CASCADE một schema test không được xoá theo nó.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

CREATE TABLE IF NOT EXISTS runs (
    run_id text PRIMARY KEY,
    uc text,
    status text,
    input jsonb,
    created_at timestamptz DEFAULT now()
);

-- Phase 2, Task 4 (UC-02b): Cache embedding để tránh gọi lặp lại (D-04, Task 4)
CREATE TABLE IF NOT EXISTS embedding_cache (
    model text NOT NULL,
    sha256 text NOT NULL,
    embedding vector(768) NOT NULL,
    created_at timestamptz DEFAULT now(),
    PRIMARY KEY (model, sha256)
);

-- Phase 2, Task 4 (UC-02b): Kho tri thức các đoạn văn bản (chunks)
CREATE TABLE IF NOT EXISTS chunks (
    id text PRIMARY KEY,
    url text NOT NULL,
    domain text NOT NULL,
    title text NOT NULL,
    published_at text,
    fetched_at text NOT NULL,
    trust_tier text NOT NULL CHECK (trust_tier IN ('A', 'B', 'C', 'brand')),
    text text NOT NULL,
    content_hash text NOT NULL,
    suspicious boolean NOT NULL DEFAULT false,
    tsv tsvector,
    embedding vector(768)
);

CREATE INDEX IF NOT EXISTS idx_chunks_url ON chunks(url);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
