-- Migration 006: Add unique constraint to prevent duplicate bullets
-- This ensures each user can only have one bullet with the same normalized text

-- Add unique index on user_id + normalized_text
-- This prevents duplicate bullets for the same user
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_bullets_unique
ON user_bullets(user_id, normalized_text);

-- Note: Before running this migration, you should:
-- 1. Run the duplicate cleanup queries to remove existing duplicates
-- 2. Verify no duplicates exist using:
--    SELECT user_id, normalized_text, COUNT(*)
--    FROM user_bullets
--    GROUP BY user_id, normalized_text
--    HAVING COUNT(*) > 1;
