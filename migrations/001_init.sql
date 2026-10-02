CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS memories(
 id uuid PRIMARY KEY, tenant_id text NOT NULL, agent_id text NOT NULL, user_id text, kind text NOT NULL CHECK(kind IN ('episodic','semantic','procedural')),
 namespace text NOT NULL DEFAULT 'default', content text NOT NULL, importance real NOT NULL DEFAULT .5, metadata jsonb NOT NULL DEFAULT '{}',
 idempotency_key text, embedding vector(384), version int NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_idem ON memories(tenant_id,idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_memory_scope ON memories(tenant_id,agent_id,namespace,kind,created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_memory_embedding ON memories USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL AND deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS memory_audit(id bigserial PRIMARY KEY,tenant_id text NOT NULL,agent_id text,action text NOT NULL,memory_id uuid,at timestamptz DEFAULT now(),metadata jsonb DEFAULT '{}');
