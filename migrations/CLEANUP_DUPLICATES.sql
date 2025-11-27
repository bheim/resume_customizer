-- =============================================================================
-- CLEANUP SCRIPT: Remove Duplicate Bullets
-- =============================================================================
-- Run this BEFORE migration 006_add_unique_constraint.sql
-- This script removes duplicate bullets and migrates their facts to the oldest bullet
-- =============================================================================

-- STEP 1: View duplicates first (SAFE - just viewing)
-- =============================================================================
SELECT
    user_id,
    normalized_text,
    COUNT(*) as duplicate_count,
    array_agg(id ORDER BY created_at) as bullet_ids,
    array_agg(created_at ORDER BY created_at) as created_dates
FROM user_bullets
GROUP BY user_id, normalized_text
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;

-- EXPECTED: You should see rows showing which bullets are duplicated


-- STEP 2: Migrate facts from duplicate bullets to the oldest one
-- =============================================================================
-- This ensures no facts are lost when we delete duplicates

WITH duplicates AS (
    SELECT
        user_id,
        normalized_text,
        array_agg(id ORDER BY created_at) as ids,
        (array_agg(id ORDER BY created_at))[1] as keep_id
    FROM user_bullets
    GROUP BY user_id, normalized_text
    HAVING COUNT(*) > 1
)
UPDATE bullet_facts
SET bullet_id = d.keep_id
FROM duplicates d
WHERE bullet_facts.bullet_id = ANY(d.ids[2:])  -- All except the first one
  AND bullet_facts.bullet_id != d.keep_id;

-- RESULT: Facts from duplicate bullets are now linked to the oldest bullet


-- STEP 3: Delete duplicate bullets (keep only the oldest)
-- =============================================================================
-- WARNING: This is DESTRUCTIVE. Make sure Step 2 completed successfully!

WITH duplicates AS (
    SELECT
        id,
        ROW_NUMBER() OVER (PARTITION BY user_id, normalized_text ORDER BY created_at) as rn
    FROM user_bullets
)
DELETE FROM user_bullets
WHERE id IN (
    SELECT id FROM duplicates WHERE rn > 1
);

-- RESULT: Only the oldest bullet remains for each unique (user_id, normalized_text) pair


-- STEP 4: Verify no duplicates remain
-- =============================================================================
SELECT
    user_id,
    normalized_text,
    COUNT(*) as count
FROM user_bullets
GROUP BY user_id, normalized_text
HAVING COUNT(*) > 1;

-- EXPECTED: No rows returned (0 duplicates)


-- STEP 5: Now you can safely run migration 006_add_unique_constraint.sql
-- =============================================================================
