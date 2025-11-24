# Resume Optimizer Refactoring Plan
## Persistent Storage & Improved Bullet Generation

---

## Overview

This refactoring adds persistent bullet storage with fact extraction and embedding-based matching to enable:
1. **One-time onboarding**: Extract facts from Q&A conversations
2. **Reusable context**: Match new bullets to existing ones using embeddings
3. **Improved generation**: Use stored facts instead of re-asking questions

---

## Database Schema Changes

### New Tables

#### 1. `user_bullets` - Store Resume Bullets with Embeddings

```sql
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
CREATE INDEX idx_user_bullets_embedding ON user_bullets USING ivfflat (bullet_embedding vector_cosine_ops) WITH (lists = 100);
```

#### 2. `bullet_facts` - Store Extracted Facts per Bullet

```sql
CREATE TABLE bullet_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bullet_id UUID NOT NULL REFERENCES user_bullets(id) ON DELETE CASCADE,
    qa_session_id UUID REFERENCES qa_sessions(id) ON DELETE SET NULL,
    facts JSONB NOT NULL, -- Structured facts extracted by LLM
    confirmed_by_user BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_bullet_facts_bullet_id ON bullet_facts(bullet_id);
CREATE INDEX idx_bullet_facts_qa_session_id ON bullet_facts(qa_session_id);
```

**Facts JSONB Structure:**
```json
{
  "metrics": {
    "quantifiable_achievements": ["Reduced deployment time by 40%", "Saved $50K annually"],
    "scale": ["Processed 10M+ requests/day", "Managed team of 5 engineers"]
  },
  "technical_details": {
    "technologies": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "methodologies": ["Agile", "CI/CD", "Test-Driven Development"]
  },
  "impact": {
    "business_outcomes": ["Improved user retention by 25%", "Accelerated feature delivery"],
    "stakeholder_value": ["Enabled marketing team to self-serve analytics"]
  },
  "context": {
    "challenges_solved": ["Legacy system migration", "Performance bottlenecks"],
    "scope": ["Cross-functional project", "6-month timeline"],
    "role": ["Technical lead", "Architected solution"]
  },
  "raw_qa": [
    {"question": "What metrics demonstrate the impact?", "answer": "Reduced deployment time from 2 hours to 45 minutes"},
    {"question": "What technologies were used?", "answer": "Built with Python, FastAPI, deployed on AWS ECS"}
  ]
}
```

#### 3. Update `qa_sessions` Table

Add column to link session to specific bullet:

```sql
ALTER TABLE qa_sessions ADD COLUMN bullet_id UUID REFERENCES user_bullets(id) ON DELETE SET NULL;
CREATE INDEX idx_qa_sessions_bullet_id ON qa_sessions(bullet_id);
```

---

## Fact Extraction Schema

### Structured Format for LLM Extraction

The LLM will convert Q&A conversations into this structured format:

```typescript
interface BulletFacts {
  metrics: {
    quantifiable_achievements: string[];  // "Reduced X by Y%", "Increased Z by N"
    scale: string[];                      // "Managed team of X", "Processed N requests/day"
  };
  technical_details: {
    technologies: string[];               // Tools, languages, frameworks
    methodologies: string[];              // Agile, TDD, CI/CD, etc.
  };
  impact: {
    business_outcomes: string[];          // Revenue, efficiency, user metrics
    stakeholder_value: string[];          // How it helped specific teams/users
  };
  context: {
    challenges_solved: string[];          // Problems addressed
    scope: string[];                      // Project size, timeline, team structure
    role: string[];                       // Your specific contributions
  };
  raw_qa: Array<{                         // Original Q&A for reference
    question: string;
    answer: string;
  }>;
}
```

---

## New Backend Components

### 1. Database Utilities (`db_utils.py`)

```python
# Bullet Management
def store_user_bullet(user_id: str, bullet_text: str, embedding: List[float], source_resume: str = None) -> str:
    """Store a bullet with its embedding. Returns bullet_id."""

def get_user_bullet(bullet_id: str) -> Dict:
    """Retrieve a bullet by ID."""

def find_similar_bullets(user_id: str, bullet_text: str, embedding: List[float], threshold: float = 0.85) -> List[Dict]:
    """
    Find bullets similar to the given text using embedding similarity.
    Returns list of matches with similarity scores, ordered by score DESC.
    """

def update_bullet_embedding(bullet_id: str, embedding: List[float]) -> None:
    """Update embedding for a bullet."""

# Fact Management
def store_bullet_facts(bullet_id: str, facts: Dict, qa_session_id: str = None, confirmed: bool = False) -> str:
    """Store extracted facts for a bullet. Returns fact_id."""

def get_bullet_facts(bullet_id: str, confirmed_only: bool = False) -> List[Dict]:
    """Retrieve facts for a bullet."""

def confirm_bullet_facts(fact_id: str) -> None:
    """Mark facts as user-confirmed."""

def update_bullet_facts(fact_id: str, facts: Dict) -> None:
    """Update facts (after user edits)."""

# Bullet Matching
def check_exact_match(user_id: str, bullet_text: str) -> Optional[str]:
    """Check for exact text match. Returns bullet_id if found."""

def match_bullet_with_confidence(user_id: str, bullet_text: str, embedding: List[float]) -> Dict:
    """
    Match bullet and return confidence level:
    {
        "match_type": "exact" | "high_confidence" | "medium_confidence" | "no_match",
        "bullet_id": str | None,
        "similarity_score": float,
        "existing_bullet_text": str | None,
        "facts": Dict | None  # If match found and facts exist
    }
    """
```

### 2. LLM Utilities (`llm_utils.py`)

```python
def extract_facts_from_qa(bullet_text: str, qa_pairs: List[Dict]) -> Dict:
    """
    Extract structured facts from Q&A conversation.

    Args:
        bullet_text: Original bullet text
        qa_pairs: List of {"question": str, "answer": str} dictionaries

    Returns:
        Structured facts following BulletFacts schema
    """

def generate_bullet_with_facts(
    original_bullet: str,
    job_description: str,
    stored_facts: Dict,
    char_limit: int
) -> str:
    """
    Generate enhanced bullet using stored facts instead of raw Q&A.

    Uses the same Google XYZ format but pulls from structured facts.
    """
```

### 3. New API Endpoints (`app.py`)

```python
# Onboarding Flow
@app.post("/onboarding/start")
async def start_onboarding(resume_file, user_id):
    """
    1. Extract bullets from resume
    2. For each bullet, check if already exists (exact or similar match)
    3. Return bullets with match status
    """

@app.post("/onboarding/confirm_match")
async def confirm_bullet_match(bullet_index, matched_bullet_id, is_same: bool):
    """
    User confirms if a similar bullet is the same or different.
    If same: link to existing facts
    If different: proceed with Q&A
    """

@app.post("/onboarding/extract_facts")
async def extract_and_confirm_facts(session_id):
    """
    1. Get all answered Q&A for session
    2. Extract structured facts using LLM
    3. Return facts for user confirmation
    """

@app.post("/onboarding/save_facts")
async def save_confirmed_facts(bullet_id, facts, confirmed: bool):
    """
    Store facts after user confirmation/editing.
    """

# Job Application Flow
@app.post("/apply/match_bullets")
async def match_bullets_for_job(resume_file, user_id):
    """
    1. Extract bullets from resume
    2. For each bullet, find best match in database
    3. Return match results with confidence levels
    """

@app.post("/apply/generate_with_facts")
async def generate_resume_with_facts(bullet_matches, job_description, original_file):
    """
    Generate optimized resume using stored facts for matched bullets.
    For new bullets, either use basic rewrite or optionally collect context.
    """
```

---

## Implementation Steps

### Phase 1: Database Setup ✅

1. **Install pgvector extension in Supabase**
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

2. **Run migrations**
   - Create `user_bullets` table
   - Create `bullet_facts` table
   - Alter `qa_sessions` to add `bullet_id` column

3. **Test schema**
   - Verify indexes created
   - Test vector similarity queries

### Phase 2: Core Utilities 🔧

1. **Extend `db_utils.py`**
   - Implement bullet storage/retrieval functions
   - Implement fact storage/retrieval functions
   - Implement similarity search using pgvector
   - Add bullet matching logic

2. **Extend `llm_utils.py`**
   - Implement `extract_facts_from_qa()` with GPT-4o-mini
   - Implement `generate_bullet_with_facts()` using structured facts
   - Update prompt templates

3. **Test utilities**
   - Unit tests for fact extraction
   - Integration tests for bullet matching
   - Test edge cases (no facts, partial facts, etc.)

### Phase 3: API Endpoints 🌐

1. **Onboarding endpoints**
   - `/onboarding/start` - Extract and match bullets
   - `/onboarding/extract_facts` - Extract facts from Q&A
   - `/onboarding/save_facts` - Store confirmed facts

2. **Application endpoints**
   - `/apply/match_bullets` - Match resume bullets to stored ones
   - `/apply/generate_with_facts` - Generate using stored facts

3. **Migration endpoints** (optional)
   - `/migrate/user_context_to_facts` - Convert existing user_context to facts

### Phase 4: Backward Compatibility 🔄

1. **Keep existing endpoints functional**
   - `/generate_questions` - Still works for new bullets
   - `/submit_answers` - Still works, but also triggers fact extraction
   - `/generate_results` - Checks for stored facts first

2. **Add feature flags**
   - `USE_PERSISTENT_FACTS` - Enable new fact-based flow
   - `FALLBACK_TO_QA` - Allow Q&A flow if no facts found

### Phase 5: Frontend Integration 📱

**Note**: Since frontend is separate (Lovable), provide integration guide:

1. **Onboarding Flow UI Components**
   ```typescript
   // 1. Bullet Match Confirmation
   <BulletMatchConfirmation
     originalBullet={bullet}
     matchedBullet={match.existing_bullet_text}
     similarityScore={match.similarity_score}
     onConfirm={(isSame) => confirmMatch(bullet, match.bullet_id, isSame)}
   />

   // 2. Fact Confirmation/Editing
   <FactEditor
     extractedFacts={facts}
     onSave={(editedFacts) => saveFacts(bulletId, editedFacts)}
   />
   ```

2. **Application Flow UI Components**
   ```typescript
   // Bullet Status Display
   <BulletMatchStatus
     bullets={bullets}
     matches={matches}
     onCollectContext={(bulletIndex) => startQAForBullet(bulletIndex)}
   />
   ```

---

## Key Design Decisions

### 1. Embedding Similarity Thresholds

- **Exact match** (normalized text): Use stored facts automatically
- **High confidence** (>0.9 similarity): Use stored facts automatically
- **Medium confidence** (0.85-0.9): Ask user to confirm match
- **Low confidence** (<0.85): Treat as new bullet

### 2. Fact Storage Strategy

- Store both **structured facts** (for generation) and **raw Q&A** (for auditability)
- User confirmation required before using facts for generation
- Facts can be edited by user before saving

### 3. Backward Compatibility

- Existing endpoints continue to work
- New endpoints are additive, not replacements
- Feature flags allow gradual rollout
- Existing `user_context` table remains for historical data

### 4. Bullet Versioning

- Each bullet is stored as a separate record (no versioning)
- If user updates a bullet significantly, it gets a new embedding
- Old bullets remain for historical reference

---

## Migration Strategy

### For Existing Users

1. **Preserve `user_context` table**
   - Don't delete existing Q&A data
   - Optionally convert to facts using LLM

2. **Gradual adoption**
   - New users: Full onboarding with facts
   - Existing users: Hybrid mode (use facts if available, else Q&A)

3. **Conversion tool**
   - Endpoint to convert user_context to bullet facts
   - Run per-user on demand or during next resume upload

---

## Testing Plan

### Unit Tests

- [ ] Fact extraction accuracy (test with sample Q&A)
- [ ] Embedding similarity matching (test with known similar/different bullets)
- [ ] Structured fact schema validation

### Integration Tests

- [ ] Full onboarding flow (upload → Q&A → facts → storage)
- [ ] Full application flow (upload → match → generate)
- [ ] Hybrid flow (some bullets with facts, some without)

### Edge Cases

- [ ] No facts available (fallback to basic rewrite)
- [ ] Partial facts (some sections empty)
- [ ] User rejects all extracted facts
- [ ] Multiple resumes for same user
- [ ] Bullet text changes slightly (still same experience)

---

## Performance Considerations

### Database Optimization

- Use pgvector's `ivfflat` index for fast similarity search
- Limit similarity searches to user's own bullets (add user_id to WHERE clause)
- Cache embeddings (don't regenerate for same text)

### API Response Times

- Fact extraction: ~2-3 seconds (LLM call)
- Bullet matching: <500ms (database query with vector index)
- Generation with facts: ~3-5 seconds (same as current Q&A flow)

### Scaling

- Embeddings cached in-memory for active sessions
- Batch bullet matching for multiple bullets
- Async fact extraction for large resumes

---

## Rollout Checklist

- [ ] Phase 1: Database migrations deployed to Supabase
- [ ] Phase 2: Core utilities implemented and tested
- [ ] Phase 3: API endpoints implemented
- [ ] Phase 4: Backward compatibility verified
- [ ] Phase 5: Frontend integration guide provided
- [ ] Documentation updated
- [ ] Feature flags configured
- [ ] Monitoring/logging added
- [ ] User testing completed
- [ ] Production deployment

---

## Next Steps

1. Review this plan with team/stakeholders
2. Get approval for schema changes
3. Begin Phase 1 implementation
4. Set up development environment for testing
5. Coordinate with frontend team (Lovable integration)
