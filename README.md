# Resume Customizer with AI Q&A Flow

An intelligent resume customization tool that uses OpenAI to tailor resume bullet points to specific job descriptions. Features an interactive Q&A flow to gather additional context for better personalization.

## Features

### Core Functionality
- **Resume Parsing**: Extracts bullet points from DOCX files (numbered lists and glyph-prefixed bullets)
- **AI Rewriting**: Uses OpenAI to rewrite bullets based on job descriptions
- **Smart Scoring**: Composite scoring system (embeddings, keyword coverage, LLM evaluation)
- **Character Management**: Enforces character limits with intelligent reprompting

### Q&A Flow (NEW)
- **Interactive Questions**: AI generates targeted follow-up questions about experience
- **Context Storage**: Stores Q&A pairs in Supabase to avoid repeat questions
- **Smart Question Generation**: Determines when enough context has been gathered
- **User Context Memory**: Remembers answers across sessions for logged-in users

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repo-url>
cd resume_customizer

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Setup

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables:
- `OPENAI_API_KEY`: Your OpenAI API key
- `SUPABASE_URL`: Your Supabase project URL (for Q&A features)
- `SUPABASE_KEY`: Your Supabase anon or service key (for Q&A features)

### 3. Database Setup (Optional - for Q&A features)

If using the Q&A flow, set up Supabase:

1. Create a Supabase project at https://supabase.com
2. Run the SQL in `supabase_schema.sql` in your Supabase SQL Editor
3. Add credentials to `.env`

### 4. Run the Server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Visit http://localhost:8000 to check health status.

## API Endpoints

### Basic Rewrite (No Q&A)

#### POST `/rewrite`
Returns modified DOCX file directly.

**Request**: `multipart/form-data`
- `file`: Resume DOCX file
- `job_description`: Target job description
- `max_chars_override` (optional): Character limit override

**Response**: DOCX file download

#### POST `/rewrite_json`
Returns modified DOCX as base64 with scoring metrics.

**Response**:
```json
{
  "file_b64": "base64-encoded-docx",
  "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "filename": "resume_edited.docx",
  "scores": {
    "before": { "embed_sim": 0.65, "keyword_cov": 0.42, "llm_score": 58.0, "composite": 54.2 },
    "after": { "embed_sim": 0.82, "keyword_cov": 0.71, "llm_score": 78.0, "composite": 76.8 },
    "delta": { "embed_sim": 0.17, "keyword_cov": 0.29, "llm_score": 20.0, "composite": 22.6 }
  }
}
```

### Q&A Flow Endpoints

#### POST `/generate_questions`
Initialize Q&A session and get first questions.

**Request**: `multipart/form-data`
- `file`: Resume DOCX file
- `job_description`: Target job description
- `user_id` (optional): User identifier

**Response**:
```json
{
  "session_id": "uuid",
  "questions": [
    { "qa_id": "uuid", "question": "What quantifiable metrics...", "type": "metrics" }
  ],
  "bullet_count": 5
}
```

#### POST `/submit_answers`
Submit answers and get next questions (if needed).

**Request**: `application/json`
```json
{
  "session_id": "uuid",
  "user_id": "user-123",
  "answers": [
    { "qa_id": "uuid", "answer": "Increased revenue by 40%..." }
  ]
}
```

**Response**:
```json
{
  "session_id": "uuid",
  "need_more_questions": true,
  "reason": "Need more technical details",
  "new_questions": [ /* ... */ ],
  "total_answered": 3,
  "ready_for_rewrite": false
}
```

#### POST `/rewrite_with_qa`
Generate improved resume using Q&A context.

**Request**: `multipart/form-data`
- `session_id`: Session ID from generate_questions
- `max_chars_override` (optional): Character limit override

**Response**:
```json
{
  "session_id": "uuid",
  "original_bullets": ["...", "..."],
  "rewritten_bullets": ["...", "..."],
  "scores": { /* same as /rewrite_json */ },
  "qa_context_used": 5
}
```

## Architecture

### Project Structure

```
resume_customizer/
├── app.py                      # FastAPI application with endpoints
├── config.py                   # Configuration and client initialization
├── llm_utils.py               # OpenAI LLM interactions
├── docx_utils.py              # DOCX parsing and manipulation
├── db_utils.py                # Supabase database operations
├── scoring.py                 # Resume scoring logic
├── caps.py                    # Character limit enforcement
├── text_utils.py              # Text processing utilities
├── requirements.txt           # Python dependencies
├── supabase_schema.sql        # Database schema for Q&A
├── .env.example              # Environment variables template
├── README.md                 # This file
└── LOVABLE_INTEGRATION.md    # Frontend integration guide
```

### How It Works

#### Basic Rewrite Flow
1. Extract bullet points from DOCX
2. Distill job description to core requirements
3. Extract role-critical terms
4. Send bullets + job context to OpenAI
5. Enforce character limits with reprompting
6. Update DOCX with new bullets
7. Calculate before/after scores

#### Q&A Flow
1. User uploads resume + job description
2. Backend extracts bullets and generates initial questions
3. Questions stored in Supabase
4. User answers questions in frontend
5. Backend determines if more questions needed
6. If yes, generate more questions; if no, mark ready
7. Backend uses all Q&A context to generate better bullets
8. Store answers in user_context for future sessions

### Question Types

The AI generates questions in these categories:
- **metrics**: Quantifiable achievements and results
- **technical**: Technologies, tools, methodologies
- **impact**: Business impact and outcomes
- **scope**: Team size, project scale, responsibilities
- **challenges**: Problems solved and obstacles overcome
- **achievements**: Notable accomplishments and recognition

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | *Required* |
| `SUPABASE_URL` | Supabase project URL | *Optional* |
| `SUPABASE_KEY` | Supabase API key | *Optional* |
| `LOG_LEVEL` | Logging level | `INFO` |
| `EMBED_MODEL` | OpenAI embedding model | `text-embedding-3-small` |
| `CHAT_MODEL` | OpenAI chat model | `gpt-4o-mini` |
| `USE_LLM_TERMS` | Use LLM for term extraction | `1` |
| `USE_DISTILLED_JD` | Distill job descriptions | `1` |
| `W_EMB` | Embedding similarity weight | `0.4` |
| `W_KEY` | Keyword coverage weight | `0.2` |
| `W_LLM` | LLM score weight | `0.4` |
| `W_DISTILLED` | Distilled JD weight | `0.7` |
| `REPROMPT_TRIES` | Max reprompt attempts | `3` |

### Scoring System

The composite score combines three metrics:

1. **Embedding Similarity** (W_EMB = 0.4)
   - Cosine similarity between resume and job description embeddings
   - Range: 0.0 to 1.0

2. **Keyword Coverage** (W_KEY = 0.2)
   - Fraction of job description terms present in resume
   - Range: 0.0 to 1.0

3. **LLM Score** (W_LLM = 0.4)
   - GPT evaluation of resume-job fit
   - Range: 0 to 100

**Composite Score** = (W_EMB × embed_sim × 100) + (W_KEY × keyword_cov × 100) + (W_LLM × llm_score)

## Frontend Integration

For detailed Lovable integration instructions, see [LOVABLE_INTEGRATION.md](./LOVABLE_INTEGRATION.md).

### Quick Example (React/TypeScript)

```typescript
// 1. Generate questions
const formData = new FormData();
formData.append('file', resumeFile);
formData.append('job_description', jobDesc);
formData.append('user_id', userId);

const { session_id, questions } = await fetch('/api/generate_questions', {
  method: 'POST',
  body: formData
}).then(r => r.json());

// 2. Submit answers (loop until ready_for_rewrite)
const { ready_for_rewrite, new_questions } = await fetch('/api/submit_answers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id,
    user_id: userId,
    answers: [{ qa_id: 'uuid', answer: 'answer text' }]
  })
}).then(r => r.json());

// 3. Get rewritten bullets
if (ready_for_rewrite) {
  const formData = new FormData();
  formData.append('session_id', session_id);

  const { rewritten_bullets, scores } = await fetch('/api/rewrite_with_qa', {
    method: 'POST',
    body: formData
  }).then(r => r.json());
}
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio httpx

# Run tests (when available)
pytest
```

### Logging

Set `LOG_LEVEL=DEBUG` for detailed logging:

```bash
export LOG_LEVEL=DEBUG
uvicorn app:app --reload
```

### Local Development

```bash
# Hot reload on code changes
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## Deployment

### Docker (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Setup

For production:
1. Set all required environment variables
2. Use a production WSGI server (e.g., Gunicorn)
3. Enable HTTPS
4. Configure CORS appropriately
5. Set up Supabase Row Level Security (RLS)

## Troubleshooting

### Common Issues

1. **"no_bullets_found" error**
   - Ensure resume has numbered bullets (1., 2., etc.) or glyph bullets (•, -, –)
   - Check that bullets are in the main document body or tables

2. **"openai_failed" error**
   - Verify `OPENAI_API_KEY` is set correctly
   - Check OpenAI API quota/billing
   - Review logs for specific error messages

3. **"supabase_not_configured" error**
   - Set `SUPABASE_URL` and `SUPABASE_KEY` in environment
   - Verify Supabase project is active
   - Check network connectivity to Supabase

4. **Character limit issues**
   - Adjust `max_chars_override` parameter
   - Increase `REPROMPT_TRIES` for more attempts
   - Review original bullet lengths

5. **Questions not relevant**
   - Ensure job description is detailed and specific
   - Check that bullets are well-formatted
   - Try with `USE_DISTILLED_JD=0` to use full JD

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

[Add your license here]

## Support

For issues or questions:
- Check logs with `LOG_LEVEL=DEBUG`
- Review [LOVABLE_INTEGRATION.md](./LOVABLE_INTEGRATION.md) for frontend help
- Open an issue on GitHub

## Roadmap

- [ ] Support for PDF resumes
- [ ] Multi-language support
- [ ] Batch processing
- [ ] Answer quality validation
- [ ] Smart question prioritization
- [ ] DOCX storage in Supabase
- [ ] WebSocket support for real-time updates
- [ ] Resume templates
- [ ] A/B testing of rewrite strategies
