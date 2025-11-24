-- Migration: Create bullet_facts table
-- Date: 2025-11-24
-- Description: Stores structured facts extracted from Q&A conversations for each bullet

CREATE TABLE bullet_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bullet_id UUID NOT NULL REFERENCES user_bullets(id) ON DELETE CASCADE,
    qa_session_id UUID REFERENCES qa_sessions(id) ON DELETE SET NULL,
    facts JSONB NOT NULL, -- Structured facts extracted by LLM
    confirmed_by_user BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_bullet_facts_bullet_id ON bullet_facts(bullet_id);
CREATE INDEX idx_bullet_facts_qa_session_id ON bullet_facts(qa_session_id);
CREATE INDEX idx_bullet_facts_confirmed ON bullet_facts(confirmed_by_user);

-- GIN index for JSONB queries (if needed to search within facts)
CREATE INDEX idx_bullet_facts_facts_gin ON bullet_facts USING GIN (facts);

-- Add trigger to automatically update updated_at
CREATE OR REPLACE FUNCTION update_bullet_facts_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_bullet_facts_timestamp
BEFORE UPDATE ON bullet_facts
FOR EACH ROW
EXECUTE FUNCTION update_bullet_facts_timestamp();

-- Comments for documentation
COMMENT ON TABLE bullet_facts IS 'Stores structured facts extracted from Q&A conversations about resume bullets';
COMMENT ON COLUMN bullet_facts.facts IS 'Structured JSON containing metrics, technical details, impact, and context';
COMMENT ON COLUMN bullet_facts.confirmed_by_user IS 'Whether user has reviewed and confirmed these facts';

-- Example facts structure:
-- {
--   "metrics": {
--     "quantifiable_achievements": ["Reduced deployment time by 40%"],
--     "scale": ["Managed team of 5 engineers"]
--   },
--   "technical_details": {
--     "technologies": ["Python", "FastAPI", "PostgreSQL"],
--     "methodologies": ["Agile", "CI/CD"]
--   },
--   "impact": {
--     "business_outcomes": ["Improved user retention by 25%"],
--     "stakeholder_value": ["Enabled marketing team to self-serve analytics"]
--   },
--   "context": {
--     "challenges_solved": ["Legacy system migration"],
--     "scope": ["Cross-functional project", "6-month timeline"],
--     "role": ["Technical lead", "Architected solution"]
--   },
--   "raw_qa": [
--     {"question": "What metrics demonstrate the impact?", "answer": "..."}
--   ]
-- }
