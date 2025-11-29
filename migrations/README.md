# Database Migrations

This directory contains SQL migration files for the resume optimizer refactoring.

## Migration Files

1. **001_enable_pgvector.sql** - Enables pgvector extension for vector embeddings
2. **002_create_user_bullets.sql** - Creates user_bullets table for storing resume bullets with embeddings
3. **003_create_bullet_facts.sql** - Creates bullet_facts table for storing extracted facts
4. **004_alter_qa_sessions.sql** - Adds bullet_id column to qa_sessions table
5. **005_similarity_search_function.sql** - Creates optimized similarity search function
6. **006_add_unique_constraint.sql** - Adds unique constraint to prevent duplicate bullets
7. **007_fix_base_resume_storage.sql** - Migrates base resume storage to BYTEA column type
8. **008_create_job_application_sessions.sql** - Creates table for session-specific resume storage

## Running Migrations

### Option 1: Supabase Dashboard (Recommended)

1. Open your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Create a new query
4. Copy and paste each migration file content **in order** (001, 002, 003, 004)
5. Run each query
6. Verify success by checking the **Database** → **Tables** section

### Option 2: Supabase CLI

```bash
# Install Supabase CLI if not already installed
npm install -g supabase

# Login to Supabase
supabase login

# Link to your project (get project ref from dashboard)
supabase link --project-ref <your-project-ref>

# Run migrations
supabase db push

# Or run individual migration files
psql $DATABASE_URL -f migrations/001_enable_pgvector.sql
psql $DATABASE_URL -f migrations/002_create_user_bullets.sql
psql $DATABASE_URL -f migrations/003_create_bullet_facts.sql
psql $DATABASE_URL -f migrations/004_alter_qa_sessions.sql
```

### Option 3: Direct PostgreSQL Connection

```bash
# Get connection string from Supabase dashboard (Settings → Database → Connection string)
export DATABASE_URL="postgresql://postgres:[password]@[host]:5432/postgres"

# Run migrations in order
psql $DATABASE_URL -f migrations/001_enable_pgvector.sql
psql $DATABASE_URL -f migrations/002_create_user_bullets.sql
psql $DATABASE_URL -f migrations/003_create_bullet_facts.sql
psql $DATABASE_URL -f migrations/004_alter_qa_sessions.sql
```

## Verification

After running migrations, verify the setup:

```sql
-- Check if pgvector is enabled
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Check tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('user_bullets', 'bullet_facts', 'qa_sessions', 'user_base_resumes', 'job_application_sessions');

-- Check indexes
SELECT indexname, tablename FROM pg_indexes
WHERE schemaname = 'public'
AND tablename IN ('user_bullets', 'bullet_facts', 'qa_sessions');

-- Test vector similarity search (should not error)
SELECT id, bullet_text,
       bullet_embedding <=> '[0,0,0,...]'::vector AS distance
FROM user_bullets
WHERE user_id = 'test'
LIMIT 1;
```

## Rollback

If you need to rollback the migrations (⚠️ **this will delete data**):

```sql
-- Drop tables in reverse order
DROP TABLE IF EXISTS bullet_facts CASCADE;
DROP TABLE IF EXISTS user_bullets CASCADE;
ALTER TABLE qa_sessions DROP COLUMN IF EXISTS bullet_id;
DROP EXTENSION IF EXISTS vector CASCADE;
```

## Schema Diagram

```
┌─────────────────┐
│  user_bullets   │
├─────────────────┤
│ id (PK)         │
│ user_id         │◄──┐
│ bullet_text     │   │
│ bullet_embedding│   │
│ normalized_text │   │
│ source_resume   │   │
│ created_at      │   │
│ updated_at      │   │
└─────────────────┘   │
         ▲            │
         │            │
         │ (FK)       │
         │            │
┌─────────────────┐   │
│  bullet_facts   │   │
├─────────────────┤   │
│ id (PK)         │   │
│ bullet_id (FK)  │───┘
│ qa_session_id   │───┐
│ facts (JSONB)   │   │
│ confirmed       │   │
│ created_at      │   │
│ updated_at      │   │
└─────────────────┘   │
                      │
                      │ (FK)
                      │
┌─────────────────┐   │
│  qa_sessions    │   │
├─────────────────┤   │
│ id (PK)         │◄──┘
│ user_id         │
│ job_description │
│ bullets (JSONB) │
│ status          │
│ bullet_id (FK)  │───┐
│ created_at      │   │
│ updated_at      │   │
└─────────────────┘   │
                      │
                      └──► Links to user_bullets
```

## Important Notes

1. **pgvector version**: Ensure your Supabase instance supports pgvector. As of 2024, all Supabase projects have pgvector available.

2. **Vector dimensions**: The migrations use 1536 dimensions to match OpenAI's `text-embedding-3-small` model. If you change the embedding model, update the dimension in `002_create_user_bullets.sql`.

3. **Index tuning**: The `ivfflat` index with `lists=100` is optimized for ~10,000 bullets per user. Adjust if needed:
   - For <1K rows: Use `lists=10`
   - For 10K-100K rows: Use `lists=100-300`
   - For >100K rows: Use `lists=500+`

4. **Backward compatibility**: All changes are additive. Existing tables (`qa_sessions`, `qa_pairs`, `user_context`) are preserved and continue to function.

## Next Steps

After running migrations:

1. Implement database utility functions in `db_utils.py`
2. Implement fact extraction in `llm_utils.py`
3. Add new API endpoints in `app.py`
4. Test with sample data

See `REFACTOR_PLAN.md` for full implementation roadmap.
