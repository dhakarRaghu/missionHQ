-- Vault semantic search: one embedding per chunk (memory.py, llm.embed).
-- 768 = models.yaml embeddings.dimensions (gemini-embedding-001 truncated from
-- its native 3072 via the OpenAI `dimensions` parameter, which the gateway
-- honors). 768 <= 2000, so an HNSW index is allowed; cosine ops match the
-- `<=>` operator used in memory.search(). NULL = not embedded yet (FTS only).
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE hq.memory_chunks ADD COLUMN embedding vector(768);
CREATE INDEX ix_memory_chunks_embedding ON hq.memory_chunks
  USING hnsw (embedding vector_cosine_ops);
