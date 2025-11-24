-- Migration: Create user_bullets table
-- Date: 2025-11-24
-- Description: Stores resume bullets with embeddings for similarity matching

CREATE TABLE user_bullets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    bullet_text TEXT NOT NULL,
    bullet_embedding VECTOR(1536), -- text-embedding-3-small produces 1536 dimensions
    normalized_text TEXT, -- lowercase, trimmed version for exact matching
    source_resume_name TEXT, -- optional: original filename
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_user_bullets_user_id ON user_bullets(user_id);
CREATE INDEX idx_user_bullets_normalized_text ON user_bullets(normalized_text);

-- Vector similarity search index (using pgvector)
-- ivfflat index for cosine similarity searches
-- lists parameter: sqrt(row_count) is a good starting point, using 100 for ~10K rows
CREATE INDEX idx_user_bullets_embedding ON user_bullets
USING ivfflat (bullet_embedding vector_cosine_ops)
WITH (lists = 100);

-- Add trigger to automatically update normalized_text
CREATE OR REPLACE FUNCTION update_normalized_bullet_text()
RETURNS TRIGGER AS $$
BEGIN
    NEW.normalized_text = LOWER(TRIM(NEW.bullet_text));
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_normalized_bullet_text
BEFORE INSERT OR UPDATE ON user_bullets
FOR EACH ROW
EXECUTE FUNCTION update_normalized_bullet_text();

-- Comments for documentation
COMMENT ON TABLE user_bullets IS 'Stores user resume bullets with embeddings for similarity matching';
COMMENT ON COLUMN user_bullets.bullet_embedding IS 'Vector embedding from OpenAI text-embedding-3-small (1536 dimensions)';
COMMENT ON COLUMN user_bullets.normalized_text IS 'Lowercase, trimmed version of bullet_text for exact matching';
COMMENT ON COLUMN user_bullets.source_resume_name IS 'Original resume filename for reference';
