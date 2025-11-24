# Local Testing Guide

Three ways to test the refactored resume optimizer locally:

---

## Option 1: Test LLM Functions Only (NO DATABASE) ⚡

**Best for:** Quick validation of fact extraction and bullet generation logic

**Requirements:**
- `OPENAI_API_KEY` environment variable only
- No Supabase setup needed

**Run:**
```bash
export OPENAI_API_KEY='sk-...'
python test_local_no_db.py
```

**Tests:**
- ✅ Fact extraction from Q&A
- ✅ Bullet generation with facts
- ✅ Embedding generation
- ✅ Similarity calculation

**Duration:** ~30 seconds

---

## Option 2: Test with Mocked Database (NO SUPABASE) 🎭

**Best for:** Testing full workflow without infrastructure setup

**Requirements:**
- `OPENAI_API_KEY` environment variable only
- No Supabase setup needed

**Run:**
```bash
export OPENAI_API_KEY='sk-...'
python test_local_with_mocks.py
```

**Tests:**
- ✅ Complete onboarding flow
- ✅ Complete job application flow
- ✅ Bullet matching with confidence levels
- ✅ Fact storage and retrieval (in-memory)
- ✅ Similarity threshold behavior

**Duration:** ~60 seconds

**What it does:**
- Simulates database operations in memory
- Tests the complete user workflow
- Shows how matching and fact reuse works
- No data persisted (resets each run)

---

## Option 3: Test with Real Supabase (FULL INTEGRATION) 🚀

**Best for:** Pre-production validation with real database

**Requirements:**
- `OPENAI_API_KEY` environment variable
- `SUPABASE_URL` environment variable
- `SUPABASE_KEY` environment variable
- Database migrations run (001-005)

**Setup:**
1. Run database migrations first:
   ```bash
   # See migrations/README.md for detailed instructions
   # Or via Supabase dashboard: SQL Editor → Run migrations
   ```

2. Set environment variables:
   ```bash
   export OPENAI_API_KEY='sk-...'
   export SUPABASE_URL='https://xxx.supabase.co'
   export SUPABASE_KEY='eyJ...'
   ```

3. Run tests:
   ```bash
   python test_with_supabase.py
   ```

**Tests:**
- ✅ Bullet storage in PostgreSQL
- ✅ Vector embedding storage
- ✅ Semantic similarity search with pgvector
- ✅ Exact, high, medium, no-match detection
- ✅ Fact storage and retrieval
- ✅ Fact confirmation workflow

**Duration:** ~90 seconds

**What it does:**
- Creates real database records
- Tests vector similarity with pgvector
- Validates database schema and indexes
- Automatically cleans up test data

---

## Recommended Testing Sequence

### 1. Start with Option 1 (No Database)
Validates core LLM functionality works:
```bash
python test_local_no_db.py
```

**Look for:**
- ✅ Fact extraction produces structured JSON
- ✅ Enhanced bullets are better than originals
- ✅ Embedding similarities make sense

---

### 2. Move to Option 2 (Mocked Database)
Tests complete workflow without infrastructure:
```bash
python test_local_with_mocks.py
```

**Look for:**
- ✅ Onboarding flow completes successfully
- ✅ Job application flow reuses facts
- ✅ Matching confidence levels are correct
- ✅ Similar bullets detected with >0.9 similarity

---

### 3. Finish with Option 3 (Real Supabase)
Validates production readiness:
```bash
# Run migrations first!
python test_with_supabase.py
```

**Look for:**
- ✅ All database operations succeed
- ✅ Vector similarity search works
- ✅ Cleanup completes without errors

---

## Interpreting Results

### Success Looks Like:

**test_local_no_db.py:**
```
✅ Fact extraction successful!
✅ Bullet generation successful!
✅ Similarity test passed!
Enhanced bullet: Architected customer analytics dashboard using React...
```

**test_local_with_mocks.py:**
```
✅ EXACT MATCH found: abc12345...
✅ HIGH CONFIDENCE match: def67890... (similarity: 0.923)
✅ Using stored facts for generation
✅ Generated 3 bullets
   - 2 used stored facts (fact-based generation)
```

**test_with_supabase.py:**
```
✅ user_bullets table exists
✅ bullet_facts table exists
✅ Stored bullet: abc12345-...
✅ Retrieved bullet: Led team of 5 engineers...
✅ PASS: Exact match detected
✅ All database tests passed!
```

### Common Issues:

**❌ "OPENAI_API_KEY not set"**
```bash
export OPENAI_API_KEY='sk-proj-...'
```

**❌ "user_bullets table not found"**
- Run database migrations first
- See `migrations/README.md`

**❌ "Similarity lower than expected"**
- Check OpenAI API key is valid
- Ensure using `text-embedding-3-small` model
- Verify embeddings are 1536 dimensions

**❌ "Failed to store bullet"**
- Check Supabase credentials
- Verify network connectivity
- Check Supabase dashboard for errors

---

## What Each Test Validates

| Test | No DB | Mocked DB | Real DB |
|------|-------|-----------|---------|
| Fact extraction | ✅ | ✅ | ✅ |
| Bullet generation | ✅ | ✅ | ✅ |
| Embedding creation | ✅ | ✅ | ✅ |
| Similarity matching | ❌ | ✅ | ✅ |
| Database storage | ❌ | ✅ (mock) | ✅ |
| Vector search | ❌ | ✅ (Python) | ✅ (pgvector) |
| Onboarding flow | ❌ | ✅ | ✅ |
| Application flow | ❌ | ✅ | ✅ |
| Production-ready | ❌ | ❌ | ✅ |

---

## Cost Estimates (OpenAI API)

All tests use OpenAI API and will incur small costs:

- **Option 1**: ~$0.02 (embedding + generation)
- **Option 2**: ~$0.10 (multiple embeddings + generations)
- **Option 3**: ~$0.05 (similar to Option 1)

Using `text-embedding-3-small` and `gpt-4o-mini` keeps costs minimal.

---

## Next Steps After Testing

Once all tests pass:

1. **Review generated bullets** - Are they high quality?
2. **Check extracted facts** - Do they capture key details?
3. **Validate matching** - Do similar bullets get matched correctly?
4. **Adjust thresholds** - Fine-tune 0.85/0.9 if needed
5. **Deploy to production** - Follow `IMPLEMENTATION_GUIDE.md`

---

## Troubleshooting

### Test hangs or times out
- Check internet connectivity
- Verify OpenAI API key is valid
- Check Supabase URL is reachable

### Embeddings don't match expected similarity
- Different embeddings models produce different results
- Ensure consistent use of `text-embedding-3-small`
- Thresholds (0.85, 0.9) may need adjustment for your use case

### Database errors in Option 3
- Verify migrations ran successfully
- Check Supabase logs in dashboard
- Ensure service role key has proper permissions

---

## Quick Reference

```bash
# Option 1: LLM functions only (30 sec)
export OPENAI_API_KEY='sk-...'
python test_local_no_db.py

# Option 2: Mocked database (60 sec)
python test_local_with_mocks.py

# Option 3: Real Supabase (90 sec)
export SUPABASE_URL='https://...'
export SUPABASE_KEY='eyJ...'
python test_with_supabase.py
```

Happy testing! 🎉
