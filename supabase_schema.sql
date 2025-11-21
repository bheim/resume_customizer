-- Supabase schema for Resume Customizer Q&A Flow

-- Table to store Q&A sessions
CREATE TABLE IF NOT EXISTS qa_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    job_description TEXT NOT NULL,
    bullets JSONB NOT NULL, -- Array of original bullet points
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status TEXT DEFAULT 'active' -- active, completed, abandoned
);

-- Table to store individual Q&A pairs
CREATE TABLE IF NOT EXISTS qa_pairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES qa_sessions(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT,
    question_type TEXT, -- experience, skills, achievements, etc.
    asked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    answered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table to store user context (for avoiding repeat questions)
CREATE TABLE IF NOT EXISTS user_context (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    question_hash TEXT NOT NULL, -- Hash of the question to avoid duplicates
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, question_hash)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_qa_sessions_user_id ON qa_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_qa_sessions_created_at ON qa_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_session_id ON qa_pairs(session_id);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_asked_at ON qa_pairs(asked_at);
CREATE INDEX IF NOT EXISTS idx_user_context_user_id ON user_context(user_id);
CREATE INDEX IF NOT EXISTS idx_user_context_question_hash ON user_context(question_hash);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at
CREATE TRIGGER update_qa_sessions_updated_at BEFORE UPDATE ON qa_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add bullet_index column to qa_pairs table (for associating questions with specific bullets)
-- Run this ALTER TABLE if bullet_index doesn't exist yet
ALTER TABLE qa_pairs ADD COLUMN IF NOT EXISTS bullet_index INTEGER;
