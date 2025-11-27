-- Migration: Fix base resume storage to use BYTEA for binary data
-- This fixes base64 corruption issues when storing resume files

-- Create the table if it doesn't exist (for new deployments)
CREATE TABLE IF NOT EXISTS user_base_resumes (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    file_data BYTEA NOT NULL,  -- Store binary data directly, not base64
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- If the table already exists with TEXT column, migrate it to BYTEA
-- First, check if file_data is currently TEXT type
DO $$
BEGIN
    -- Check if column exists and is TEXT type
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'user_base_resumes'
        AND column_name = 'file_data'
        AND data_type = 'text'
    ) THEN
        -- Column is TEXT, we need to convert it
        -- First, decode the base64 data to bytes
        ALTER TABLE user_base_resumes
        ADD COLUMN file_data_new BYTEA;

        -- Convert base64 TEXT to BYTEA
        UPDATE user_base_resumes
        SET file_data_new = decode(file_data, 'base64');

        -- Drop old column and rename new one
        ALTER TABLE user_base_resumes DROP COLUMN file_data;
        ALTER TABLE user_base_resumes RENAME COLUMN file_data_new TO file_data;

        -- Make it NOT NULL
        ALTER TABLE user_base_resumes ALTER COLUMN file_data SET NOT NULL;

        RAISE NOTICE 'Converted file_data from TEXT to BYTEA';
    ELSE
        RAISE NOTICE 'file_data column is already BYTEA or does not exist';
    END IF;
END $$;

-- Ensure updated_at is properly set
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_user_base_resumes_updated_at ON user_base_resumes;
CREATE TRIGGER update_user_base_resumes_updated_at
    BEFORE UPDATE ON user_base_resumes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create index on user_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_base_resumes_user_id ON user_base_resumes(user_id);
