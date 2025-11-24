# Prompt for Lovable: Migrate to New Conversational Resume Optimizer

---

## Context

I have an existing resume optimizer app built with Lovable that currently works with a Q&A-based backend. The backend has been completely refactored to use:

1. **Persistent bullet storage** with semantic matching
2. **Conversational AI** instead of formal Q&A
3. **Fact-based bullet generation** with XYZ format
4. **Job description keyword extraction**

I need you to update the frontend to work with the new backend API while preserving the existing UX where appropriate.

---

## Current State (What Needs to Change)

### Old Flow:
1. User uploads resume
2. Backend extracts bullets
3. User answers formal Q&A questions
4. Backend generates enhanced bullets
5. User downloads resume

### Problems:
- No bullet reuse across job applications
- Formal Q&A feels rigid
- No persistent storage
- User re-answers same questions for each job

---

## New Architecture

### Backend API Endpoints

All endpoints are under `/v2/` prefix on the backend API.

#### **Add Context Flow** (Conversational)

**1. POST /v2/context/start**
```typescript
// Request
{
  user_id: string,
  bullet_text: string,
  bullet_id?: string,  // optional, if adding to existing
  job_description?: string  // optional, helps generate better questions
}

// Response
{
  session_id: string,
  bullet_id: string,
  bullet_text: string,
  questions: Array<{
    question: string,
    type: string,
    id: string  // qa_id for answering
  }>,
  message: string
}
```

**2. POST /v2/context/answer**
```typescript
// Request
{
  session_id: string,
  answers: Array<{
    qa_id: string,
    answer: string
  }>
}

// Response (Auto-stop logic)
{
  status: "continue" | "complete",
  next_questions?: Array<{question, type, id}>,  // if continue
  extracted_facts?: {  // if complete
    situation: string,
    actions: string[],
    results: string[],
    skills: string[],
    tools: string[],
    timeline: string
  },
  fact_id?: string,  // if complete
  message: string
}
```

**3. POST /v2/context/confirm_facts**
```typescript
// Request (FormData)
{
  fact_id: string,
  edited_facts?: string  // JSON string if user edited
}

// Response
{
  status: "success",
  message: string,
  fact_id: string
}
```

#### **Job Application Flow**

**1. POST /v2/apply/match_bullets**
```typescript
// Request (FormData)
{
  user_id: string,
  resume_file: File
}

// Response
{
  bullets: string[],
  matches: Array<{
    bullet_index: number,
    bullet_text: string,
    match_type: "exact" | "high_confidence" | "medium_confidence" | "no_match",
    bullet_id?: string,
    similarity_score?: number,
    existing_bullet_text?: string,
    has_facts: boolean,
    facts?: object
  }>
}
```

**2. POST /v2/apply/generate_with_facts**
```typescript
// Request
{
  user_id: string,
  job_description: string,
  bullets: string[]
}

// Response
{
  enhanced_bullets: string[],
  bullets_with_facts: number[],  // indices
  bullets_without_facts: number[]  // indices
}
```

---

## Required UI Changes

### 1. **Add Context Button on Each Bullet**

When user views their bullets (either after upload or in their saved bullets), show an "Add Context" button next to each bullet.

**Behavior:**
- Click "Add Context" → Opens conversational dialog
- AI asks 1-2 questions at a time
- User answers (can skip)
- AI automatically decides if more questions needed
- When done → Shows extracted facts for review
- User confirms → Facts saved

**Component Example:**
```tsx
function BulletWithContext({ bullet, userId }) {
  const [showContextDialog, setShowContextDialog] = useState(false);

  return (
    <div className="bullet-item">
      <p>{bullet.text}</p>
      <button onClick={() => setShowContextDialog(true)}>
        {bullet.has_facts ? "Edit Context" : "Add Context"}
      </button>

      {showContextDialog && (
        <AddContextDialog
          bulletText={bullet.text}
          bulletId={bullet.id}
          userId={userId}
          onClose={() => setShowContextDialog(false)}
        />
      )}
    </div>
  );
}
```

### 2. **Conversational Dialog Component**

Replace formal Q&A with conversational interface.

**Key Features:**
- Shows 1-2 questions at a time (not all at once)
- Textarea for natural responses
- "Skip" and "Submit" buttons
- AI auto-stops when it has enough
- Shows extracted facts for review
- Allows editing facts before confirming

**Component Structure:**
```tsx
function AddContextDialog({ bulletText, userId, onClose }) {
  const [sessionId, setSessionId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [extractedFacts, setExtractedFacts] = useState(null);
  const [loading, setLoading] = useState(false);

  // Step 1: Start conversation
  const startContext = async () => {
    setLoading(true);
    const res = await fetch('/v2/context/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, bullet_text: bulletText })
    });
    const data = await res.json();
    setSessionId(data.session_id);
    setQuestions(data.questions);
    setLoading(false);
  };

  // Step 2: Submit answers
  const submitAnswers = async () => {
    setLoading(true);
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
      // More questions
      setQuestions(data.next_questions);
      setAnswers({});  // Clear for new questions
    } else {
      // Complete - show facts
      setExtractedFacts(data.extracted_facts);
    }
    setLoading(false);
  };

  // Step 3: Confirm facts
  const confirmFacts = async () => {
    const formData = new FormData();
    formData.append('fact_id', extractedFacts.fact_id);

    await fetch('/v2/context/confirm_facts', {
      method: 'POST',
      body: formData
    });

    onClose();  // Close dialog
  };

  return (
    <Dialog open onClose={onClose}>
      {!sessionId && (
        <div>
          <h2>Add Context: {bulletText}</h2>
          <button onClick={startContext}>Start</button>
        </div>
      )}

      {sessionId && !extractedFacts && (
        <div>
          <h3>Tell me more...</h3>
          {questions.map(q => (
            <div key={q.id}>
              <label>{q.question}</label>
              <textarea
                value={answers[q.id] || ''}
                onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })}
                rows={4}
                placeholder="Share as much detail as you'd like..."
              />
            </div>
          ))}
          <button onClick={submitAnswers} disabled={loading}>
            {loading ? "Processing..." : "Submit"}
          </button>
          <button onClick={() => setAnswers({})}>Skip These</button>
        </div>
      )}

      {extractedFacts && (
        <div>
          <h3>Review Extracted Facts</h3>
          <FactsReview facts={extractedFacts} />
          <button onClick={confirmFacts}>Confirm & Save</button>
          <button onClick={() => setExtractedFacts(null)}>Edit Answers</button>
        </div>
      )}
    </Dialog>
  );
}
```

### 3. **Facts Review Component**

Show extracted facts in readable format for user confirmation.

```tsx
function FactsReview({ facts }) {
  return (
    <div className="facts-review">
      {facts.situation && (
        <div>
          <h4>Situation/Context</h4>
          <p>{facts.situation}</p>
        </div>
      )}

      {facts.actions?.length > 0 && (
        <div>
          <h4>Actions</h4>
          <ul>
            {facts.actions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}

      {facts.results?.length > 0 && (
        <div>
          <h4>Results</h4>
          <ul>
            {facts.results.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {facts.skills?.length > 0 && (
        <div>
          <h4>Skills</h4>
          <p>{facts.skills.join(', ')}</p>
        </div>
      )}

      {facts.tools?.length > 0 && (
        <div>
          <h4>Tools/Technologies</h4>
          <p>{facts.tools.join(', ')}</p>
        </div>
      )}
    </div>
  );
}
```

### 4. **Bullet Matching Status (Job Application)**

When user uploads resume for a job, show which bullets have stored facts.

```tsx
function BulletMatchStatus({ matches }) {
  return (
    <div className="bullet-matches">
      <h3>Your Resume Bullets</h3>
      {matches.map((match, idx) => (
        <div key={idx} className={`match-${match.match_type}`}>
          <p>{match.bullet_text}</p>

          {match.match_type === "exact" && (
            <span className="badge success">✓ Exact Match - Using stored facts</span>
          )}

          {match.match_type === "high_confidence" && (
            <span className="badge success">✓ High Confidence Match - Using stored facts</span>
          )}

          {match.match_type === "medium_confidence" && (
            <span className="badge warning">
              ⚠ Similar to: "{match.existing_bullet_text}"
              <button>Confirm Same</button>
              <button>Different Experience</button>
            </span>
          )}

          {match.match_type === "no_match" && (
            <span className="badge info">
              ℹ New bullet - No stored facts
              <button>Add Context</button>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
```

### 5. **Updated Job Application Flow**

```tsx
function JobApplicationFlow({ userId }) {
  const [step, setStep] = useState('upload'); // upload, match, generate, download
  const [resumeFile, setResumeFile] = useState(null);
  const [jobDescription, setJobDescription] = useState('');
  const [matches, setMatches] = useState([]);
  const [enhancedBullets, setEnhancedBullets] = useState([]);

  // Step 1: Upload resume
  const handleUpload = async () => {
    const formData = new FormData();
    formData.append('user_id', userId);
    formData.append('resume_file', resumeFile);

    const res = await fetch('/v2/apply/match_bullets', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    setMatches(data.matches);
    setStep('match');
  };

  // Step 2: Generate with facts
  const handleGenerate = async () => {
    const bullets = matches.map(m => m.bullet_text);

    const res = await fetch('/v2/apply/generate_with_facts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        job_description: jobDescription,
        bullets: bullets
      })
    });
    const data = await res.json();

    setEnhancedBullets(data.enhanced_bullets);
    setStep('download');
  };

  return (
    <div>
      {step === 'upload' && (
        <div>
          <input type="file" onChange={e => setResumeFile(e.target.files[0])} />
          <textarea
            placeholder="Paste job description..."
            value={jobDescription}
            onChange={e => setJobDescription(e.target.value)}
          />
          <button onClick={handleUpload}>Upload & Match</button>
        </div>
      )}

      {step === 'match' && (
        <div>
          <BulletMatchStatus matches={matches} />
          <button onClick={handleGenerate}>Generate Resume</button>
        </div>
      )}

      {step === 'download' && (
        <div>
          <h3>Enhanced Resume</h3>
          {enhancedBullets.map((bullet, i) => (
            <p key={i}>{bullet}</p>
          ))}
          <button>Download DOCX</button>
        </div>
      )}
    </div>
  );
}
```

---

## Implementation Priority

1. **First:** Add Context dialog (most important UX change)
2. **Second:** Bullet matching status display
3. **Third:** Job application flow with facts
4. **Fourth:** Facts review/editing component

---

## Key UX Principles

✅ **Conversational, not formal** - Questions feel like a friendly interview
✅ **Progressive disclosure** - Show 1-2 questions at a time, not overwhelming
✅ **Smart auto-stop** - AI decides when enough context gathered
✅ **User control** - Can skip questions, edit facts, confirm before saving
✅ **Visual feedback** - Clear indicators of which bullets have facts
✅ **Reuse emphasis** - Show value of stored facts (faster next time!)

---

## Migration Strategy

### Phase 1: Keep Old Flow Working
- Don't break existing upload/download
- Add new "Add Context" as optional feature
- Users can still use basic flow without context

### Phase 2: Add New Features
- Implement Add Context dialog
- Add bullet matching display
- Show which bullets have facts

### Phase 3: Make New Flow Primary
- Encourage users to add context
- Show benefits (faster, better results)
- Gradual transition from old to new

---

## API Base URL

Configure in your frontend:
```typescript
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

---

## Testing Checklist

- [ ] Add Context dialog opens and closes
- [ ] Questions display one at a time
- [ ] Answers submit successfully
- [ ] AI auto-stop works (status="complete")
- [ ] Extracted facts display correctly
- [ ] Facts can be edited before confirming
- [ ] Bullet matching shows correct confidence levels
- [ ] Job application generates with stored facts
- [ ] Download still works

---

## Questions to Consider

1. **Styling:** Should match your existing design system
2. **Loading states:** Show spinners during API calls
3. **Error handling:** What if API call fails?
4. **Mobile:** How should dialog look on mobile?
5. **Accessibility:** Keyboard navigation, screen readers

---

## Summary for Lovable

Please update my resume optimizer frontend to support the new conversational backend API. The key changes are:

1. Add "Add Context" button on each bullet that opens a conversational dialog
2. Dialog shows 1-2 questions at a time, AI auto-stops when enough context
3. Show extracted facts for user review/confirmation
4. Display bullet matching status when uploading resume for job
5. Use stored facts automatically for matched bullets

Keep the existing upload/download flow working, but add these new features alongside. Make the UX feel conversational and friendly, not formal Q&A.

API endpoints are all under `/v2/` and documented above. Let me know if you need clarification on any endpoint or component!
