# Setup Guide for Resume Customizer

This guide walks you through setting up the resume customizer with Supabase integration.

## Prerequisites

- Python 3.9+
- OpenAI API key
- Supabase account (free tier works)

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Set Up Supabase

### 2.1 Access Your Supabase Project

Your Supabase credentials are already configured in `.env`:
- URL: `https://grfdmtjytugaoychtxpr.supabase.co`
- Key: Already set in `.env`

### 2.2 Create Database Tables

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor** (in the left sidebar)
3. Click **New Query**
4. Copy the entire contents of `supabase_schema.sql`
5. Paste into the query editor
6. Click **Run** (or press Ctrl/Cmd + Enter)

This will create three tables:
- `qa_sessions` - Stores Q&A sessions with bullets and job descriptions
- `qa_pairs` - Stores individual questions and answers
- `user_context` - Stores user's historical Q&A to avoid repeat questions

### 2.3 Verify Tables Were Created

In the Supabase dashboard:
1. Go to **Table Editor** (left sidebar)
2. You should see three new tables:
   - `qa_sessions`
   - `qa_pairs`
   - `user_context`

## Step 3: Configure Environment Variables

The `.env` file is already configured with Supabase credentials. You just need to add your OpenAI API key:

1. Open `.env`
2. Replace `sk-your-openai-api-key-here` with your actual OpenAI API key
3. Save the file

Example:
```bash
OPENAI_API_KEY=sk-proj-abc123...
```

## Step 4: Test the Setup

### 4.1 Start the Server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2 Check Health Status

Visit http://localhost:8000 in your browser or:

```bash
curl http://localhost:8000
```

You should see:
```json
{
  "status": "ok",
  "openai": true,
  "supabase": true,
  "models": {...},
  ...
}
```

**Important**: Both `"openai": true` and `"supabase": true` should be present.

## Step 5: Test the Q&A Flow

### 5.1 Generate Questions

```bash
curl -X POST http://localhost:8000/generate_questions \
  -F "file=@your-resume.docx" \
  -F "job_description=Senior Software Engineer position requiring Python, React, and AWS experience. Lead cross-functional teams..." \
  -F "user_id=test-user-123"
```

Expected response:
```json
{
  "session_id": "uuid-here",
  "questions": [
    {
      "qa_id": "uuid-here",
      "question": "What quantifiable metrics or results did you achieve?",
      "type": "metrics"
    },
    ...
  ],
  "bullet_count": 5
}
```

**Save the `session_id`** - you'll need it for the next steps.

### 5.2 Submit Answers

```bash
curl -X POST http://localhost:8000/submit_answers \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "your-session-id-from-above",
    "user_id": "test-user-123",
    "answers": [
      {
        "qa_id": "qa-id-from-questions",
        "answer": "Increased revenue by 40% ($2M) through ML optimization"
      },
      {
        "qa_id": "another-qa-id",
        "answer": "Used Python, TensorFlow, AWS SageMaker, and React"
      }
    ]
  }'
```

Expected response:
```json
{
  "session_id": "uuid",
  "need_more_questions": false,
  "reason": "Sufficient context gathered",
  "new_questions": [],
  "total_answered": 2,
  "ready_for_rewrite": true
}
```

If `ready_for_rewrite: true`, proceed to the next step. If `need_more_questions: true`, answer the `new_questions` and submit again.

### 5.3 Get Rewritten Bullets

```bash
curl -X POST http://localhost:8000/rewrite_with_qa \
  -F "session_id=your-session-id"
```

Expected response:
```json
{
  "session_id": "uuid",
  "original_bullets": ["...", "..."],
  "rewritten_bullets": [
    "Increased revenue by 40% ($2M) as measured by quarterly reports by implementing ML optimization using Python and TensorFlow on AWS",
    "..."
  ],
  "scores": {
    "before": {...},
    "after": {...},
    "delta": {...}
  },
  "qa_context_used": 2
}
```

## Step 6: Verify Database Storage

Check that data was stored correctly:

1. Go to Supabase **Table Editor**
2. Click on `qa_sessions` - you should see your session
3. Click on `qa_pairs` - you should see your questions and answers
4. Click on `user_context` - you should see the Q&A stored for the user

## Troubleshooting

### "supabase_not_configured" Error

**Problem**: Supabase client failed to initialize.

**Solutions**:
1. Check that `SUPABASE_URL` and `SUPABASE_KEY` are correct in `.env`
2. Verify you can access your Supabase project dashboard
3. Check the server logs for initialization errors:
   ```bash
   LOG_LEVEL=DEBUG uvicorn app:app --reload
   ```

### "openai_failed" Error

**Problem**: OpenAI API call failed.

**Solutions**:
1. Verify `OPENAI_API_KEY` is correct in `.env`
2. Check OpenAI API quota/billing at https://platform.openai.com/usage
3. Check server logs for specific error messages

### "no_bullets_found" Error

**Problem**: Could not extract bullets from DOCX.

**Solutions**:
1. Ensure your resume has numbered bullets (1., 2., 3., etc.) or glyph bullets (•, -, –)
2. Check that bullets are in the main document body (not just headers)
3. Try a different DOCX file to verify the parser works

### "session_not_found" Error

**Problem**: Session ID doesn't exist or was deleted.

**Solutions**:
1. Verify you're using the correct `session_id` from `/generate_questions`
2. Check Supabase `qa_sessions` table to see if the session exists
3. Generate a new session if needed

### Database Connection Issues

**Problem**: Cannot connect to Supabase.

**Solutions**:
1. Check internet connection
2. Verify Supabase project is active (not paused)
3. Try accessing Supabase dashboard directly
4. Check if Supabase is experiencing outages: https://status.supabase.com

### Tables Not Found

**Problem**: Queries fail with "relation does not exist" errors.

**Solutions**:
1. Run `supabase_schema.sql` in Supabase SQL Editor
2. Verify tables were created in Table Editor
3. Check that you're using the correct Supabase project URL

## Next Steps

### For Lovable Integration

See [LOVABLE_INTEGRATION.md](./LOVABLE_INTEGRATION.md) for detailed frontend integration instructions.

### For Production Deployment

1. **Environment Variables**: Set all variables in your hosting platform
2. **Database Security**: Configure Supabase Row Level Security (RLS) policies
3. **API Keys**: Use separate OpenAI keys for dev/prod
4. **Monitoring**: Set up logging and error tracking
5. **CORS**: Update CORS settings in `app.py` for your frontend domain

### Optional Enhancements

1. **File Storage**: Store original DOCX in Supabase Storage
2. **User Authentication**: Integrate Supabase Auth
3. **Rate Limiting**: Add rate limiting to API endpoints
4. **Caching**: Cache job description analysis results
5. **Analytics**: Track usage metrics and success rates

## Support

For issues:
1. Check server logs: `LOG_LEVEL=DEBUG uvicorn app:app --reload`
2. Review Supabase logs in dashboard
3. Check OpenAI API logs at https://platform.openai.com/account/api-keys
4. Review this setup guide and [LOVABLE_INTEGRATION.md](./LOVABLE_INTEGRATION.md)

## Quick Reference Commands

```bash
# Start server
uvicorn app:app --reload

# Start with debug logging
LOG_LEVEL=DEBUG uvicorn app:app --reload

# Check health
curl http://localhost:8000

# Install dependencies
pip install -r requirements.txt

# Test with example resume
curl -X POST http://localhost:8000/generate_questions \
  -F "file=@resume.docx" \
  -F "job_description=Job description here..." \
  -F "user_id=test-user"
```
