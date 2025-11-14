# Resume Customizer - Lovable Integration Guide

## Overview

This resume customizer has been enhanced with an interactive Q&A flow that allows the AI to ask follow-up questions before generating improved resume bullets. All Q&A data is stored in Supabase to avoid asking users the same questions repeatedly.

## Architecture

### Flow Diagram

```
1. User uploads resume (DOCX) + job description
   ↓
2. Backend extracts bullets → Generates initial questions
   ↓
3. Questions stored in Supabase & returned to frontend
   ↓
4. User answers questions in Lovable UI
   ↓
5. Answers submitted to backend & stored in Supabase
   ↓
6. AI determines if more questions needed
   ↓
   - If YES: Generate & return new questions (go to step 3)
   - If NO: Mark session as "ready_for_rewrite"
   ↓
7. Frontend calls rewrite endpoint with session_id
   ↓
8. Backend uses Q&A context to generate improved bullets
```

## API Endpoints

### 1. POST `/generate_questions`

**Purpose**: Initialize Q&A session and generate first set of questions

**Request**:
- **Content-Type**: `multipart/form-data`
- **Parameters**:
  - `file`: Resume file (DOCX)
  - `job_description`: Job description text
  - `user_id` (optional): User identifier to avoid repeat questions

**Response**:
```json
{
  "session_id": "uuid-string",
  "questions": [
    {
      "qa_id": "uuid-string",
      "question": "What quantifiable metrics...",
      "type": "metrics"
    }
  ],
  "bullet_count": 5
}
```

**Example Usage (JavaScript)**:
```javascript
const formData = new FormData();
formData.append('file', resumeFile);
formData.append('job_description', jobDesc);
formData.append('user_id', userId || 'anonymous');

const response = await fetch('https://your-backend.com/generate_questions', {
  method: 'POST',
  body: formData
});

const data = await response.json();
// data.session_id - Save this for subsequent requests
// data.questions - Display these in your UI
```

### 2. POST `/submit_answers`

**Purpose**: Submit user answers and get next set of questions (if needed)

**Request**:
- **Content-Type**: `application/json`
- **Body**:
```json
{
  "session_id": "uuid-string",
  "user_id": "user-123",
  "answers": [
    {
      "qa_id": "uuid-string",
      "answer": "User's answer text..."
    }
  ]
}
```

**Response**:
```json
{
  "session_id": "uuid-string",
  "need_more_questions": true,
  "reason": "Need more technical details",
  "new_questions": [
    {
      "qa_id": "uuid-string",
      "question": "What specific technologies...",
      "type": "technical"
    }
  ],
  "total_answered": 3,
  "ready_for_rewrite": false
}
```

**Example Usage (JavaScript)**:
```javascript
const response = await fetch('https://your-backend.com/submit_answers', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    session_id: sessionId,
    user_id: userId,
    answers: [
      { qa_id: 'qa-1', answer: 'Increased revenue by 40%...' },
      { qa_id: 'qa-2', answer: 'Used Python, React, AWS...' }
    ]
  })
});

const data = await response.json();

if (data.need_more_questions) {
  // Display new_questions in UI
} else if (data.ready_for_rewrite) {
  // Proceed to rewrite step
}
```

### 3. POST `/rewrite_with_qa`

**Purpose**: Generate improved resume bullets using Q&A context

**Request**:
- **Content-Type**: `multipart/form-data`
- **Parameters**:
  - `session_id`: Session ID from generate_questions
  - `max_chars_override` (optional): Character limit override

**Response**:
```json
{
  "session_id": "uuid-string",
  "original_bullets": ["...", "..."],
  "rewritten_bullets": ["...", "..."],
  "scores": {
    "before": {
      "embed_sim": 0.65,
      "keyword_cov": 0.42,
      "llm_score": 58.0,
      "composite": 54.2
    },
    "after": {
      "embed_sim": 0.82,
      "keyword_cov": 0.71,
      "llm_score": 78.0,
      "composite": 76.8
    },
    "delta": {
      "embed_sim": 0.17,
      "keyword_cov": 0.29,
      "llm_score": 20.0,
      "composite": 22.6
    }
  },
  "qa_context_used": 5
}
```

**Example Usage (JavaScript)**:
```javascript
const formData = new FormData();
formData.append('session_id', sessionId);

const response = await fetch('https://your-backend.com/rewrite_with_qa', {
  method: 'POST',
  body: formData
});

const data = await response.json();
// data.rewritten_bullets - Show to user
// data.scores - Display improvement metrics
```

## Supabase Setup

### Required Tables

Run the SQL script in `supabase_schema.sql` to create the required tables:

```bash
# In Supabase SQL Editor, run:
cat supabase_schema.sql
```

### Tables Created:

1. **qa_sessions**: Stores Q&A sessions
   - `id` (UUID): Session identifier
   - `user_id` (TEXT): User identifier
   - `job_description` (TEXT): Target job description
   - `bullets` (JSONB): Original resume bullets
   - `status` (TEXT): Session status (active, ready_for_rewrite, completed)

2. **qa_pairs**: Stores individual Q&A pairs
   - `id` (UUID): Q&A pair identifier
   - `session_id` (UUID): Foreign key to qa_sessions
   - `question` (TEXT): Question text
   - `answer` (TEXT): Answer text (null if unanswered)
   - `question_type` (TEXT): Type of question (metrics, technical, etc.)

3. **user_context**: Stores historical Q&A to avoid repeats
   - `id` (UUID): Context identifier
   - `user_id` (TEXT): User identifier
   - `question_hash` (TEXT): Hash of question
   - `question` (TEXT): Question text
   - `answer` (TEXT): Answer text

## Environment Variables

Create a `.env` file with the following variables:

```bash
# Required
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-service-key

# Optional - Defaults shown
LOG_LEVEL=INFO
EMBED_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
USE_LLM_TERMS=1
USE_DISTILLED_JD=1
```

## Frontend Integration (Lovable)

### Recommended Component Structure

```typescript
// types.ts
interface Question {
  qa_id: string;
  question: string;
  type: string;
}

interface Answer {
  qa_id: string;
  answer: string;
}

// ResumeCustomizer.tsx
import { useState } from 'react';

export function ResumeCustomizer() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [isComplete, setIsComplete] = useState(false);
  const [rewrittenBullets, setRewrittenBullets] = useState<string[]>([]);

  // Step 1: Upload resume and get initial questions
  const handleUpload = async (file: File, jobDesc: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('job_description', jobDesc);
    formData.append('user_id', getUserId()); // Your user ID logic

    const res = await fetch('/api/generate_questions', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    setSessionId(data.session_id);
    setQuestions(data.questions);
  };

  // Step 2: Submit answers
  const handleSubmitAnswers = async () => {
    const answerList = questions.map(q => ({
      qa_id: q.qa_id,
      answer: answers[q.qa_id] || ''
    }));

    const res = await fetch('/api/submit_answers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        user_id: getUserId(),
        answers: answerList
      })
    });

    const data = await res.json();

    if (data.need_more_questions) {
      // Add new questions to the list
      setQuestions([...questions, ...data.new_questions]);
      setAnswers({}); // Clear answers for new questions
    } else if (data.ready_for_rewrite) {
      setIsComplete(true);
    }
  };

  // Step 3: Get rewritten resume
  const handleRewrite = async () => {
    const formData = new FormData();
    formData.append('session_id', sessionId!);

    const res = await fetch('/api/rewrite_with_qa', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    setRewrittenBullets(data.rewritten_bullets);
  };

  return (
    <div>
      {!sessionId && (
        <UploadForm onUpload={handleUpload} />
      )}

      {sessionId && !isComplete && (
        <QuestionForm
          questions={questions}
          answers={answers}
          onAnswerChange={(qaId, value) =>
            setAnswers({ ...answers, [qaId]: value })
          }
          onSubmit={handleSubmitAnswers}
        />
      )}

      {isComplete && !rewrittenBullets.length && (
        <button onClick={handleRewrite}>
          Generate Improved Resume
        </button>
      )}

      {rewrittenBullets.length > 0 && (
        <ResultsDisplay bullets={rewrittenBullets} />
      )}
    </div>
  );
}
```

### Key Points for Lovable Integration

1. **Session Management**:
   - Save `session_id` after the first call to `/generate_questions`
   - Use this `session_id` for all subsequent calls

2. **User ID Handling**:
   - Pass a consistent `user_id` to avoid asking repeat questions
   - Can use "anonymous" if user is not logged in

3. **Question Loop**:
   - After submitting answers, check `need_more_questions`
   - If `true`, display `new_questions` and repeat
   - If `false` and `ready_for_rewrite` is `true`, proceed to rewrite

4. **Storing Q&A Context**:
   - All Q&A pairs are automatically stored in Supabase
   - For logged-in users, answers are stored in `user_context`
   - Future sessions will check this context and avoid asking the same questions

5. **Error Handling**:
   - Check response status codes
   - Handle cases where Supabase is not configured (503 error)
   - Display user-friendly error messages

## Testing the Flow

### Using cURL

1. **Generate questions**:
```bash
curl -X POST http://localhost:8000/generate_questions \
  -F "file=@resume.docx" \
  -F "job_description=Senior Software Engineer..." \
  -F "user_id=test-user-123"
```

2. **Submit answers**:
```bash
curl -X POST http://localhost:8000/submit_answers \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "your-session-id",
    "user_id": "test-user-123",
    "answers": [
      {
        "qa_id": "qa-id-1",
        "answer": "Increased revenue by 40% through optimization"
      }
    ]
  }'
```

3. **Get rewritten bullets**:
```bash
curl -X POST http://localhost:8000/rewrite_with_qa \
  -F "session_id=your-session-id"
```

## Deployment Notes

### Environment Setup

1. Set up Supabase project at https://supabase.com
2. Run the `supabase_schema.sql` script in Supabase SQL Editor
3. Get your Supabase URL and anon/service key
4. Set environment variables in your hosting platform

### Required Dependencies

Install Python dependencies:
```bash
pip install -r requirements.txt
```

### Running the Server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Future Enhancements

1. **File Storage**: Store the original DOCX in Supabase Storage to return modified DOCX directly from `/rewrite_with_qa`
2. **User Authentication**: Integrate with Supabase Auth for proper user management
3. **Question Categories**: Add filtering/grouping of questions by type
4. **Progress Tracking**: Show progress bar based on question completion
5. **Answer Validation**: Validate answer quality before accepting
6. **Smart Question Ordering**: Prioritize most important questions first
7. **Batch Processing**: Allow multiple resume uploads and parallel Q&A sessions

## Troubleshooting

### Common Issues

1. **"supabase_not_configured" error**:
   - Ensure `SUPABASE_URL` and `SUPABASE_KEY` are set in environment
   - Check that Supabase client is initialized (check `/` endpoint health check)

2. **"session_not_found" error**:
   - Verify session_id is correct
   - Check if session exists in `qa_sessions` table

3. **Questions not generating**:
   - Check OpenAI API key is valid
   - Review logs for LLM errors
   - Ensure job description and bullets are not empty

4. **Duplicate questions**:
   - Ensure `user_id` is consistent across sessions
   - Check `user_context` table for stored Q&A pairs

## Support

For issues or questions:
- Check the logs: `LOG_LEVEL=DEBUG` for detailed debugging
- Review Supabase dashboard for database issues
- Check OpenAI API usage/quota
