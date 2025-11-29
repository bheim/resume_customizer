-- Migration: Create job_application_sessions table
-- This table stores uploaded resumes for specific job application sessions
-- Allows users to upload a custom resume per job application that differs from base resume

CREATE TABLE IF NOT EXISTS job_application_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    resume_data TEXT NOT NULL,  -- Hex-encoded resume data (\x...)
    resume_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on session_id for fast lookups
CREATE INDEX IF NOT EXISTS idx_job_application_sessions_session_id
    ON job_application_sessions(session_id);

-- Create index on user_id for user-specific queries
CREATE INDEX IF NOT EXISTS idx_job_application_sessions_user_id
    ON job_application_sessions(user_id);

-- Create trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_job_application_sessions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_job_application_sessions_updated_at
    ON job_application_sessions;

CREATE TRIGGER update_job_application_sessions_updated_at
    BEFORE UPDATE ON job_application_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_job_application_sessions_updated_at();

-- Add comment explaining the table
COMMENT ON TABLE job_application_sessions IS
    'Stores resume files uploaded for specific job application sessions. '
    'resume_data is hex-encoded (\x...) for consistency with BYTEA columns.';
