-- Migration: Alter qa_sessions to link to user_bullets
-- Date: 2025-11-24
-- Description: Adds bullet_id column to qa_sessions to link Q&A sessions to specific bullets

-- Add bullet_id column to qa_sessions
ALTER TABLE qa_sessions
ADD COLUMN bullet_id UUID REFERENCES user_bullets(id) ON DELETE SET NULL;

-- Create index for performance
CREATE INDEX idx_qa_sessions_bullet_id ON qa_sessions(bullet_id);

-- Add comment for documentation
COMMENT ON COLUMN qa_sessions.bullet_id IS 'Links Q&A session to a specific bullet in user_bullets table';

-- Note: This column will be NULL for existing sessions (backward compatible)
-- New sessions can optionally link to a bullet when facts are being collected
