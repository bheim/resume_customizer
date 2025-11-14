# Render Deployment Troubleshooting Guide

## Quick Checklist

If your Render deployment isn't working, check these in order:

### 1. ✅ Environment Variables

Go to your Render dashboard → your service → Environment

**Required variables:**
```
OPENAI_API_KEY=sk-...                    # Your OpenAI key
SUPABASE_URL=https://grfdmtjytugaoychtxpr.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # Your Supabase anon key
```

**Optional but recommended:**
```
LOG_LEVEL=INFO
EMBED_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
USE_LLM_TERMS=1
USE_DISTILLED_JD=1
```

### 2. ✅ Build Settings

In Render dashboard → Settings:

**Build Command:**
```bash
pip install -r requirements.txt
```

**Start Command:**
```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

**Python Version:** `3.11.9` (or set in runtime.txt)

### 3. ✅ Check Logs

In Render dashboard → Logs, look for:

**Successful startup:**
```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:XXXX
```

**Common errors and fixes below** ⬇️

## Common Error Messages & Solutions

### Error: "Supabase credentials not found"

**Log shows:**
```
WARNING:  Supabase credentials not found. Q&A features will be disabled.
```

**Solution:**
1. Go to Render dashboard → Environment
2. Add `SUPABASE_URL` and `SUPABASE_KEY`
3. Click "Save Changes"
4. Render will automatically redeploy

### Error: "OPENAI_API_KEY missing"

**Log shows:**
```
RuntimeError: OPENAI_API_KEY missing
```

**Solution:**
1. Go to Render dashboard → Environment
2. Add `OPENAI_API_KEY=sk-your-key-here`
3. Save and redeploy

### Error: "Port already in use" or "Address already in use"

**Cause:** Not using Render's `$PORT` variable

**Solution:**
Update Start Command to:
```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

### Error: "ModuleNotFoundError: No module named 'X'"

**Cause:** Missing dependency in requirements.txt

**Solution:**
1. Check your local `requirements.txt`
2. Make sure it includes all dependencies
3. Push to GitHub
4. Render will auto-redeploy

### Error: 503 Service Unavailable

**Possible causes:**
1. Service is still starting (wait 1-2 minutes)
2. Build failed (check Logs)
3. Health check failing
4. Out of memory

**Solutions:**
- Check Logs for specific errors
- Verify environment variables are set
- Check if using correct Python version
- May need to upgrade to higher Render tier if memory issues

### Error: "cannot import name 'X' from 'Y'"

**Cause:** Python version mismatch or dependency conflict

**Solution:**
1. Add `runtime.txt` with `python-3.11.9`
2. Verify requirements.txt has no conflicts
3. Check Logs for specific import errors

### Error: CORS issues from frontend

**Frontend shows:**
```
Access to XMLHttpRequest blocked by CORS policy
```

**Solution:**
The app already has CORS enabled for all origins:
```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
```

If still having issues:
1. Check frontend is using correct API URL
2. Verify it's using `https://` not `http://`
3. Check Render logs for OPTIONS requests

### Error: Health check endpoints failing

**Render can't reach your app**

**Solution:**
1. Verify Start Command uses `--host 0.0.0.0`
2. Check app is listening on `$PORT`
3. Test health endpoint: `curl https://your-app.onrender.com/`

Expected response:
```json
{
  "status": "ok",
  "openai": true,
  "supabase": true,
  ...
}
```

## Testing Your Deployment

### 1. Test Health Endpoint

```bash
curl https://your-app-name.onrender.com/
```

Expected: `{"status": "ok", "openai": true, "supabase": true, ...}`

### 2. Test Question Generation

```bash
curl -X POST https://your-app-name.onrender.com/generate_questions \
  -F "file=@resume.docx" \
  -F "job_description=Test job" \
  -F "user_id=test"
```

Expected: `{"session_id": "...", "questions": [...], ...}`

### 3. Check Logs

Look for:
```
INFO:     Supabase client initialized successfully
INFO:     Started server process
INFO:     Application startup complete
```

## Step-by-Step Deployment from Scratch

### Option 1: Using render.yaml (Recommended)

1. **Push code to GitHub** (already done)

2. **In Render Dashboard:**
   - Click "New +"
   - Select "Blueprint"
   - Connect your GitHub repo
   - Select the branch: `claude/resume-customizer-ai-flow-011CV4M4QK4GNy5HjJSWB6MC`
   - Render will read `render.yaml` automatically

3. **Add Secret Environment Variables:**
   - `OPENAI_API_KEY` (add manually, not in render.yaml)
   - `SUPABASE_KEY` (add manually)

4. **Deploy**
   - Render will build and deploy automatically
   - Watch logs for any errors

### Option 2: Manual Setup

1. **In Render Dashboard:**
   - Click "New +"
   - Select "Web Service"
   - Connect your GitHub repo
   - Select branch: `claude/resume-customizer-ai-flow-011CV4M4QK4GNy5HjJSWB6MC`

2. **Configure Settings:**
   - **Name:** resume-customizer
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`

3. **Add Environment Variables:**
   ```
   OPENAI_API_KEY=sk-...
   SUPABASE_URL=https://grfdmtjytugaoychtxpr.supabase.co
   SUPABASE_KEY=eyJhbGci...
   LOG_LEVEL=INFO
   ```

4. **Create Service**
   - Click "Create Web Service"
   - Wait for build to complete (2-5 minutes)

## Specific Endpoint Issues

### `/generate_questions` returns 503

**Check:**
1. Supabase credentials are set
2. OpenAI API key is valid
3. File upload size isn't too large (Render free tier has limits)

**Debug:**
Look in logs for:
```
ERROR: Failed to create Q&A session
ERROR: openai_failed
ERROR: supabase_not_configured
```

### `/submit_answers` returns 404 "session_not_found"

**Cause:** Session expired or invalid session_id

**Solution:**
1. Check session_id is correct
2. Verify Supabase tables exist (run supabase_schema.sql)
3. Check Supabase logs in dashboard

### `/rewrite_with_qa` returns 502

**Cause:** OpenAI API timeout or error

**Solution:**
1. Check OpenAI API key is valid
2. Check OpenAI API status: https://status.openai.com
3. May need longer timeout (upgrade Render tier)
4. Check logs for specific OpenAI error

## Debugging Tips

### Enable Debug Logging

Add environment variable:
```
LOG_LEVEL=DEBUG
```

This will show detailed logs including:
- All API calls
- Supabase queries
- OpenAI requests
- Error stack traces

### Check Supabase Tables

1. Go to Supabase dashboard
2. Table Editor → verify tables exist:
   - `qa_sessions`
   - `qa_pairs`
   - `user_context`

3. Run query to check data:
```sql
SELECT * FROM qa_sessions ORDER BY created_at DESC LIMIT 5;
```

### Test Locally First

Before debugging on Render, test locally:

```bash
# Set environment variables
export OPENAI_API_KEY=sk-...
export SUPABASE_URL=https://grfdmtjytugaoychtxpr.supabase.co
export SUPABASE_KEY=eyJhbGci...

# Run locally
uvicorn app:app --reload

# Test endpoint
curl http://localhost:8000/
```

If it works locally but not on Render → environment variable issue

### Common Gotchas

1. **Environment variables not saved**: Click "Save Changes" in Render dashboard
2. **Old build cached**: Manual deploy or clear cache
3. **Wrong branch deployed**: Check branch in Render settings
4. **Supabase RLS blocking**: Disable RLS for testing (not recommended for production)
5. **File size limits**: Render free tier has request size limits

## Performance Issues

### Slow response times

**Solutions:**
1. Upgrade Render plan (more CPU/RAM)
2. Use faster OpenAI model (gpt-4o-mini already fast)
3. Cache job description analysis
4. Reduce `max_questions` in code

### Timeout errors

**Solutions:**
1. Increase timeout in frontend
2. Upgrade Render plan
3. Optimize prompts to be shorter
4. Use streaming responses (requires code changes)

## Need More Help?

**Check these in order:**

1. ✅ Render Logs (most important!)
2. ✅ Supabase logs (Database → Logs)
3. ✅ OpenAI API logs (platform.openai.com)
4. ✅ Test health endpoint
5. ✅ Test locally with same environment variables

**Share these when asking for help:**
- Specific error message from Render logs
- Environment variables (values redacted)
- Which endpoint is failing
- Request/response examples

## Working Deployment Checklist

Use this to verify everything is working:

- [ ] Can access health endpoint: `https://your-app.onrender.com/`
- [ ] Health endpoint returns `"openai": true`
- [ ] Health endpoint returns `"supabase": true`
- [ ] Can upload DOCX file without error
- [ ] Questions are generated successfully
- [ ] Can submit answers without error
- [ ] Can get rewritten bullets
- [ ] Bullets are in Google XYZ format
- [ ] Scores are calculated correctly
- [ ] No errors in Render logs
- [ ] Response times are acceptable (< 30s for rewrites)

## Contact Render Support

If still stuck, contact Render support with:
- Link to your service
- Error logs (copy/paste specific errors)
- What you've tried already
- Expected vs actual behavior
