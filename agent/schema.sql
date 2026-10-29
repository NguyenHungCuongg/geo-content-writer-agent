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
