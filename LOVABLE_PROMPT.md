# Build Resume Optimizer Frontend with Conversational AI

## What You're Building

A React frontend for a resume optimizer that uses conversational AI to gather context about resume bullets, then automatically reuses that context across multiple job applications.

**The backend API is already running.** You only need to build the React UI that calls these endpoints.

---

## The Complete User Flow

### Flow 1: First Time Using the App

1. **Upload Resume** → Extract bullets from DOCX
2. **Show Bullets** → User sees list of their resume bullets
3. **Add Context** (optional) → User clicks "Add Context" on any bullet
   - Conversational AI asks 1-2 questions at a time
   - User answers naturally (can skip questions)
   - AI automatically decides when it has enough information
   - Shows extracted facts for user to review/confirm
   - Facts saved to database for future use

### Flow 2: Applying for a Job

1. **Upload Resume + Job Description** → System matches bullets
2. **Show Matching Status** → For each bullet, show:
   - ✅ "Has context" (green badge) - if facts exist
   - ⚠️ "Add context for better results" (yellow badge) - if no facts
3. **Generate Optimized Resume** → System automatically uses stored facts
4. **Download** → Get enhanced DOCX

---

## Backend API Endpoints (Already Implemented)

Base URL: Use environment variable `VITE_API_URL` (defaults to `http://localhost:8000`)

### 1️⃣ Upload & Extract Bullets

**POST `/upload`**

```typescript
// FormData request
{
  file: File,  // DOCX file
  user_id: string
}

// Response
{
  bullets: string[],
  message: string
}
```

### 2️⃣ Start Conversational Context Gathering

**POST `/qa/start`**

```typescript
// JSON request
{
  user_id: string,
  bullets: string[],
  job_description: string
}

// Response
{
  session_id: string,
  questions: Array<{
    question: string,
    type: string,
    bullet_index: number,
    bullet_text: string
  }>,
  message: string
}
```

### 3️⃣ Submit Answers (AI Auto-Decides if More Needed)

**POST `/qa/answer`**

```typescript
// JSON request
{
  session_id: string,
  answers: Array<{
    question: string,
    answer: string
  }>
}

// Response - Option A: Need more questions
{
  status: "continue",
  questions: Array<{question, type, bullet_index, bullet_text}>,
  message: string
}

// Response - Option B: Done gathering context
{
  status: "complete",
  message: string
}
```

### 4️⃣ Generate Optimized Resume

**POST `/generate`**

```typescript
// JSON request
{
  user_id: string,
  bullets: string[],
  job_description: string,
  session_id: string  // from qa/start
}

// Response
{
  enhanced_bullets: string[],
  message: string
}
```

### 5️⃣ Download DOCX

**POST `/download`**

```typescript
// FormData request
{
  bullets: string[],  // JSON stringified array
  user_id: string
}

// Response
DOCX file (application/vnd.openxmlformats-officedocument.wordprocessingml.document)
```

---

## Components to Build

### 1. `ResumeUploader` Component

```typescript
interface ResumeUploaderProps {
  onBulletsExtracted: (bullets: string[], sessionId?: string) => void;
}
```

**UI:**
- File input for DOCX upload
- Textarea for job description (required)
- "Extract Bullets" button
- Loading spinner during upload
- Error message display

**Behavior:**
- User uploads DOCX and enters job description
- Call `POST /upload` to extract bullets
- Call `POST /qa/start` to begin Q&A session
- Pass bullets and sessionId to parent component

### 2. `ConversationalQA` Component

```typescript
interface ConversationalQAProps {
  sessionId: string;
  initialQuestions: Question[];
  onComplete: () => void;
}

interface Question {
  question: string;
  type: string;
  bullet_index: number;
  bullet_text: string;
}
```

**UI:**
- Title: "Let's add some context to strengthen your bullets"
- Show current bullet being discussed (from `bullet_text`)
- Display 1-2 questions at a time (not all at once!)
- Large textarea for each answer (4-5 rows)
- "Skip this question" button (optional)
- "Submit Answers" button
- Progress indicator (e.g., "Question 2 of 5")

**Behavior:**
- Display questions from props
- User types answers naturally
- On submit → Call `POST /qa/answer`
- If response.status === "continue" → Show next questions
- If response.status === "complete" → Call `onComplete()`

**Key UX Points:**
- Conversational tone, not formal
- Allow skipping questions
- Show which bullet the question is about
- Don't overwhelm with too many questions at once

### 3. `BulletsList` Component

```typescript
interface BulletsListProps {
  bullets: string[];
  sessionId?: string;
  onRegenerateClick: () => void;
}
```

**UI:**
- Title: "Your Resume Bullets"
- List each bullet with:
  - Bullet text
  - Badge showing if context exists (check via sessionId)
  - "Add More Context" button (opens ConversationalQA again)
- "Generate Optimized Resume" button at bottom

**Behavior:**
- Display all bullets
- If sessionId exists, show ✅ "Context added" badge
- Click "Add More Context" → Opens Q&A dialog again
- Click "Generate" → Call parent to generate resume

### 4. `EnhancedResume` Component

```typescript
interface EnhancedResumeProps {
  originalBullets: string[];
  enhancedBullets: string[];
  userId: string;
}
```

**UI:**
- Title: "Your Optimized Resume"
- Side-by-side comparison (optional but nice):
  - Left: Original bullet
  - Right: Enhanced bullet
- "Download DOCX" button
- "Start Over" button

**Behavior:**
- Display enhanced bullets
- Download button → Call `POST /download` with enhanced bullets
- Trigger browser download of DOCX file

### 5. `App` Component (Main Container)

```typescript
function App() {
  const [step, setStep] = useState('upload'); // upload, qa, bullets, enhanced
  const [userId, setUserId] = useState(() => generateUserId());
  const [bullets, setBullets] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [jobDescription, setJobDescription] = useState('');
  const [enhancedBullets, setEnhancedBullets] = useState([]);
}
```

**Flow:**
1. Start at "upload" step → Show ResumeUploader
2. After upload → Set bullets, sessionId, questions → Move to "qa" step
3. Show ConversationalQA → User answers questions
4. When complete → Move to "bullets" step
5. User clicks "Generate" → Call `/generate` → Move to "enhanced" step
6. Show EnhancedResume → User downloads

---

## Implementation Checklist

### Setup
- [ ] Create React app with TypeScript (if not already done)
- [ ] Add environment variable `VITE_API_URL` (default: `http://localhost:8000`)
- [ ] Install dependencies: `axios` or `fetch` for API calls

### Components
- [ ] Build `ResumeUploader` component
- [ ] Build `ConversationalQA` component
- [ ] Build `BulletsList` component
- [ ] Build `EnhancedResume` component
- [ ] Build `App` container with state management

### API Integration
- [ ] Implement `POST /upload` call
- [ ] Implement `POST /qa/start` call
- [ ] Implement `POST /qa/answer` call (handle both "continue" and "complete")
- [ ] Implement `POST /generate` call
- [ ] Implement `POST /download` call (trigger file download)

### UX Polish
- [ ] Add loading states for all API calls
- [ ] Add error handling and error messages
- [ ] Add success notifications
- [ ] Make conversational Q&A feel friendly (use casual language)
- [ ] Add progress indicators
- [ ] Make responsive for mobile

---

## Important Notes

### DO Build:
✅ React components with state management
✅ API calls to the endpoints listed above
✅ Loading states and error handling
✅ File upload and download functionality
✅ Conversational, friendly UI for Q&A

### DO NOT Build:
❌ Backend API endpoints (already done)
❌ Database setup (already done)
❌ AI prompts or LLM logic (backend handles this)
❌ Bullet extraction logic (backend handles this)
❌ DOCX parsing or generation (backend handles this)

### Key UX Principles

**Conversational, Not Formal**
- Questions should feel like a friendly interview
- Use warm, encouraging language
- Don't make it feel like a form to fill out

**Progressive Disclosure**
- Show 1-2 questions at a time
- Don't overwhelm with a long list
- Let the AI decide when to stop asking

**User Control**
- Always allow skipping questions
- Let users go back and add more context later
- Show clear progress and status

**Transparency**
- Show which bullets have context
- Explain what the system is doing
- Display before/after comparison

---

## Example API Usage

```typescript
// 1. Upload resume
const formData = new FormData();
formData.append('file', resumeFile);
formData.append('user_id', userId);

const uploadRes = await fetch(`${API_URL}/upload`, {
  method: 'POST',
  body: formData
});
const { bullets } = await uploadRes.json();

// 2. Start Q&A
const qaStartRes = await fetch(`${API_URL}/qa/start`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: userId,
    bullets: bullets,
    job_description: jobDescription
  })
});
const { session_id, questions } = await qaStartRes.json();

// 3. Submit answers
const qaAnswerRes = await fetch(`${API_URL}/qa/answer`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: session_id,
    answers: answers  // [{question, answer}, ...]
  })
});
const result = await qaAnswerRes.json();

if (result.status === 'continue') {
  // Show more questions
  setQuestions(result.questions);
} else {
  // Done! Move to next step
  setStep('bullets');
}

// 4. Generate enhanced resume
const generateRes = await fetch(`${API_URL}/generate`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: userId,
    bullets: bullets,
    job_description: jobDescription,
    session_id: session_id
  })
});
const { enhanced_bullets } = await generateRes.json();

// 5. Download DOCX
const downloadFormData = new FormData();
downloadFormData.append('bullets', JSON.stringify(enhanced_bullets));
downloadFormData.append('user_id', userId);

const blob = await fetch(`${API_URL}/download`, {
  method: 'POST',
  body: downloadFormData
}).then(r => r.blob());

// Trigger download
const url = window.URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = 'optimized_resume.docx';
a.click();
```

---

## That's It!

Build the React frontend that calls these 5 endpoints. The backend handles all the AI, database, and file processing. Focus on making the conversational Q&A feel natural and friendly.

The key innovation is the conversational flow with auto-stop: the AI automatically decides when it has enough context, so users don't have to answer unnecessary questions.
