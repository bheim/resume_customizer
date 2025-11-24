-- Migration: Create optimized similarity search function
-- Date: 2025-11-24
-- Description: PostgreSQL function for efficient vector similarity search

-- Function to find similar bullets using pgvector
CREATE OR REPLACE FUNCTION find_similar_bullets(
    p_user_id TEXT,
    p_embedding VECTOR(1536),
    p_threshold FLOAT DEFAULT 0.85,
    p_limit INT DEFAULT 5
)
RETURNS TABLE (
    bullet_id UUID,
    bullet_text TEXT,
    similarity_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        id AS bullet_id,
        bullet_text,
        -- Convert cosine distance to cosine similarity: similarity = 1 - distance
        (1 - (bullet_embedding <=> p_embedding))::FLOAT AS similarity_score
    FROM user_bullets
    WHERE
        user_id = p_user_id
        AND bullet_embedding IS NOT NULL
        -- Filter by threshold (convert similarity threshold to distance threshold)
        AND (bullet_embedding <=> p_embedding) <= (1 - p_threshold)
    ORDER BY bullet_embedding <=> p_embedding ASC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;

-- Add comment
COMMENT ON FUNCTION find_similar_bullets IS 'Find bullets similar to a given embedding using cosine similarity';

-- Example usage:
-- SELECT * FROM find_similar_bullets(
--     'user123',
--     '[0.1, 0.2, ...]'::vector,
--     0.85,
--     5
-- );
