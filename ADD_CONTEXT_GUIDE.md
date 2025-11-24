# "Add Context" Feature Guide

## Overview

The "Add Context" feature allows users to have a conversational AI session to add details about a resume bullet. The AI automatically knows when to stop asking questions and extract facts.

---

## How It Works

### 1. User Clicks "Add Context"

Frontend calls: `POST /v2/context/start`

```json
{
  "user_id": "user123",
  "bullet_text": "Led development of customer analytics dashboard",
  "bullet_id": null,  // or existing ID
  "job_description": "Senior Data Engineer..."  // optional
}
```

**Response:**
```json
{
  "session_id": "session-abc",
  "bullet_id": "bullet-xyz",
  "bullet_text": "Led development of customer analytics dashboard",
  "questions": [
    {
      "question": "What quantifiable metrics demonstrate the impact?",
      "type": "metrics",
      "id": "qa-1"
    },
    {
      "question": "What specific technologies did you use?",
      "type": "technical",
      "id": "qa-2"
    }
  ],
  "message": "Generated 5 questions. Answer as many as you'd like - you can skip any."
}
```

---

### 2. User Answers Questions

User types answers in conversational UI, then submits.

Frontend calls: `POST /v2/context/answer`

```json
{
  "session_id": "session-abc",
  "answers": [
    {
      "qa_id": "qa-1",
      "answer": "Reduced report generation from 2 hours to 15 minutes. Used by 50+ stakeholders daily."
    },
    {
      "qa_id": "qa-2",
      "answer": "Built with React, Python FastAPI, PostgreSQL. Deployed on AWS."
    }
  ]
}
```

**AI Decides: Need More or Done?**

The AI uses `should_ask_more_questions()` to evaluate:
- ✅ Do we have metrics?
- ✅ Do we know the technologies?
- ✅ Do we understand the impact?
- ❌ Missing: team size, project scope

---

### 3a. If AI Says: "Need More"

**Response (status="continue"):**
```json
{
  "status": "continue",
  "next_questions": [
    {
      "question": "How large was the team working on this?",
      "type": "scope",
      "id": "qa-3"
    },
    {
      "question": "What was the project timeline?",
      "type": "scope",
      "id": "qa-4"
    }
  ],
  "message": "Thanks! Just a few more questions to get the full picture. (2 questions)"
}
```

**Frontend shows more questions** → User answers → Loop back to step 2

---

### 3b. If AI Says: "Done!"

**Response (status="complete"):**
```json
{
  "status": "complete",
  "extracted_facts": {
    "metrics": {
      "quantifiable_achievements": [
        "Reduced report generation time from 2 hours to 15 minutes"
      ],
      "scale": ["Used by 50+ stakeholders daily", "Team of 3 engineers"]
    },
    "technical_details": {
      "technologies": ["React", "Python", "FastAPI", "PostgreSQL", "AWS"],
      "methodologies": ["Agile"]
    },
    "impact": {
      "business_outcomes": ["Enabled self-serve analytics"],
      "stakeholder_value": ["Freed up data team for strategic work"]
    },
    "context": {
      "challenges_solved": ["Manual reporting bottleneck"],
      "scope": ["6-month project", "Cross-functional team"],
      "role": ["Led development"]
    }
  },
  "fact_id": "fact-456",
  "message": "Great! I've gathered enough context. Review the extracted facts below."
}
```

**Frontend shows extracted facts** → User reviews/edits → Confirms

---

### 4. User Confirms Facts

Frontend calls: `POST /v2/context/confirm_facts`

```json
{
  "fact_id": "fact-456",
  "edited_facts": null  // or JSON string if user edited
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Facts confirmed! These will be used for future resumes.",
  "fact_id": "fact-456"
}
```

---

## Auto-Stop Logic

The AI evaluates based on:

### Questions It Asks Itself:
1. **Do we have quantifiable achievements?** (metrics, numbers, percentages)
2. **Do we know the technologies used?** (tools, languages, frameworks)
3. **Is the business impact clear?** (revenue, efficiency, user metrics)
4. **Do we understand the scope?** (team size, timeline, scale)
5. **Are there obvious gaps?** (missing context, vague descriptions)

### Decision Criteria:
- **STOP (status="complete")** if:
  - ✅ Has at least 1-2 quantifiable metrics
  - ✅ Technologies are specified
  - ✅ Business impact is described
  - ✅ No critical missing information

- **CONTINUE (status="continue")** if:
  - ❌ Metrics are vague or missing
  - ❌ Technologies unclear
  - ❌ Impact not quantified
  - ❌ Major gaps in context

### Bias: Conservative Stopping
The AI is **biased towards stopping** to avoid over-questioning. It will only ask for more if there are **clear, critical gaps**.

---

## Frontend Implementation Example

### React Component

```tsx
import { useState } from 'react';

function AddContextDialog({ bulletText, userId }) {
  const [sessionId, setSessionId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [extractedFacts, setExtractedFacts] = useState(null);

  // Step 1: Start session
  const startContext = async () => {
    const res = await fetch('/v2/context/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, bullet_text: bulletText })
    });
    const data = await res.json();
    setSessionId(data.session_id);
    setQuestions(data.questions);
  };

  // Step 2: Submit answers
  const submitAnswers = async () => {
    const answersList = questions.map(q => ({
      qa_id: q.id,
      answer: answers[q.id] || ''
    }));

    const res = await fetch('/v2/context/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, answers: answersList })
    });
    const data = await res.json();

    if (data.status === 'continue') {
      // More questions needed
      setQuestions(data.next_questions);
      setAnswers({});  // Reset for new questions
    } else {
      // Complete! Show facts
      setExtractedFacts(data.extracted_facts);
    }
  };

  // Step 3: Confirm facts
  const confirmFacts = async () => {
    await fetch('/v2/context/confirm_facts', {
      method: 'POST',
      body: new FormData([['fact_id', extractedFacts.fact_id]])
    });
    // Close dialog, refresh UI
  };

  return (
    <div>
      {!sessionId && <button onClick={startContext}>Add Context</button>}

      {sessionId && !extractedFacts && (
        <div>
          <h3>Tell me more about this experience:</h3>
          {questions.map(q => (
            <div key={q.id}>
              <label>{q.question}</label>
              <textarea
                value={answers[q.id] || ''}
                onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })}
              />
            </div>
          ))}
          <button onClick={submitAnswers}>Submit</button>
        </div>
      )}

      {extractedFacts && (
        <div>
          <h3>Review Extracted Facts:</h3>
          <pre>{JSON.stringify(extractedFacts, null, 2)}</pre>
          <button onClick={confirmFacts}>Confirm</button>
        </div>
      )}
    </div>
  );
}
```

---

## Key Features

✅ **Conversational**: Feels like chatting with AI, not filling a form
✅ **Auto-stop**: AI knows when it has enough context
✅ **Skip-friendly**: User can skip questions, AI adapts
✅ **Iterative**: AI can ask follow-ups based on answers
✅ **Fact extraction**: Automatically structures information
✅ **User review**: Facts shown for confirmation/editing before storage

---

## Testing the Flow

```bash
# 1. Start context session
curl -X POST http://localhost:8000/v2/context/start \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "bullet_text": "Led development of analytics dashboard"
  }'

# Response: session_id, questions

# 2. Submit answers
curl -X POST http://localhost:8000/v2/context/answer \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<session_id>",
    "answers": [
      {"qa_id": "<qa_id_1>", "answer": "Reduced time from 2hrs to 15min"},
      {"qa_id": "<qa_id_2>", "answer": "React, Python, PostgreSQL"}
    ]
  }'

# Response: Either more questions or extracted facts

# 3. Confirm facts (if complete)
curl -X POST http://localhost:8000/v2/context/confirm_facts \
  -F "fact_id=<fact_id>"
```

---

## Summary

The "Add Context" feature:
1. **User clicks** → AI generates questions
2. **User answers** → AI evaluates if enough
3. **AI decides**:
   - Need more? → Ask follow-ups
   - Enough? → Extract & show facts
4. **User confirms** → Facts stored for future use

**AI automatically stops when it has enough context** using the existing `should_ask_more_questions()` logic! 🎉
