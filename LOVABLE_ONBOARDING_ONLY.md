# Build Onboarding Flow - Resume Upload + AI Questions

## What You're Building

A simple onboarding flow where:
1. User uploads their resume (DOCX file)
2. System extracts bullets from the resume
3. For EACH bullet, AI asks conversational questions
4. User answers the questions
5. AI extracts facts and shows them for confirmation
6. Facts are saved to database

**This is ONLY the onboarding flow.** Backend API is already running at `http://localhost:8000`.

---

## The Exact User Journey

### Screen 1: Welcome & Upload

**Component:** `OnboardingUpload.tsx`

**What the user sees:**
```
┌─────────────────────────────────────┐
│  Welcome to Resume Optimizer        │
│                                     │
│  Let's start by uploading your      │
│  resume so we can learn about       │
│  your experience.                   │
│                                     │
│  [  Drag & drop DOCX file here  ]  │
│  [     or click to browse       ]   │
│                                     │
│  [      Upload Resume      ]  ←─ Button │
└─────────────────────────────────────┘
```

**What happens:**
1. User uploads DOCX file
2. Click "Upload Resume"
3. Call API: `POST /upload` with file and user_id
4. Get response: `{ bullets: ["Managed team of 5...", "Increased revenue by..."] }`
5. Go to Screen 2

**API Call Code:**
```typescript
const formData = new FormData();
formData.append('file', resumeFile);
formData.append('user_id', userId);

const response = await fetch('http://localhost:8000/upload', {
  method: 'POST',
  body: formData
});

const { bullets } = await response.json();
// bullets is array of strings
```

---

### Screen 2: Show Extracted Bullets

**Component:** `OnboardingBulletsPreview.tsx`

**What the user sees:**
```
┌─────────────────────────────────────────────┐
│  Great! We found 8 bullets in your resume   │
│                                             │
│  1. Managed team of 5 engineers...          │
│  2. Increased revenue by 40% through...     │
│  3. Led implementation of new CRM...        │
│  4. Reduced customer churn by 25%...        │
│  5. Designed and deployed microservices...  │
│  6. Collaborated with product team...       │
│  7. Optimized database queries...           │
│  8. Conducted code reviews...               │
│                                             │
│  Next, I'll ask a few questions about       │
│  each bullet to gather context.             │
│                                             │
│  [  Start Adding Context  ]  ←─ Button      │
└─────────────────────────────────────────────┘
```

**What happens:**
1. Display all extracted bullets as numbered list
2. User clicks "Start Adding Context"
3. Go to Screen 3 (start with first bullet)

---

### Screen 3: Conversational Questions (ONE BULLET AT A TIME)

**Component:** `OnboardingConversation.tsx`

**What the user sees:**
```
┌─────────────────────────────────────────────────┐
│  Progress: Bullet 1 of 8                        │
│                                                 │
│  Current Bullet:                                │
│  ┌───────────────────────────────────────────┐ │
│  │ Managed team of 5 engineers to deliver   │ │
│  │ product features on time                  │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  AI: Tell me more about this - what was the    │
│      biggest challenge you faced managing      │
│      this team?                                 │
│                                                 │
│  Your Answer:                                   │
│  ┌───────────────────────────────────────────┐ │
│  │ [Large text area for user to type]        │ │
│  │                                            │ │
│  │                                            │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  [  Skip This Bullet  ]                         │
│  [  Skip Question  ]   [  Submit Answer  ]      │
└─────────────────────────────────────────────────┘
```

**What happens - STEP BY STEP:**

**STEP 1:** When this screen loads for a bullet:
```typescript
// Call this API when showing a new bullet
const response = await fetch('http://localhost:8000/v2/context/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: userId,
    bullet_text: bullets[currentBulletIndex]  // e.g., bullets[0]
  })
});

const { session_id, initial_question } = await response.json();

// Display initial_question to user
// Save session_id in state
```

**STEP 2:** User types an answer and clicks "Submit Answer":
```typescript
// Call this API when user submits answer
const response = await fetch('http://localhost:8000/v2/context/answer', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: sessionId,  // from STEP 1
    user_answer: userAnswer  // what user typed
  })
});

const result = await response.json();

// Check the status field
if (result.status === 'continue') {
  // AI wants to ask more questions
  // Display result.next_question to user
  // User answers again, call /v2/context/answer again
  // Repeat until status === 'complete'
}

if (result.status === 'complete') {
  // AI has enough information
  // result.extracted_facts contains the facts
  // Go to Screen 4 to show facts
}
```

**STEP 3:** Keep asking questions until `status === 'complete'`

**The conversation might look like:**
```
AI Q1: "Tell me more about this - what was the biggest challenge?"
User A1: "The biggest challenge was coordinating across time zones..."

AI Q2: "What specific results did you achieve?"
User A2: "We delivered 3 major features and reduced bugs by 30%"

AI: ✓ "Thanks! I have enough context."
→ Go to Screen 4
```

**STEP 4: SKIP THIS BULLET** (if user doesn't have additional context)

**IMPORTANT:** User can click "Skip This Bullet" button at any time to skip adding context for this bullet entirely.

**What happens when user clicks "Skip This Bullet":**
```typescript
const handleSkipBullet = () => {
  // Don't save any facts for this bullet
  // Move directly to the next bullet
  const nextIndex = currentBulletIndex + 1;

  if (nextIndex < bullets.length) {
    // More bullets to process - go to next bullet
    onSkipBullet();  // Parent component moves to next bullet
  } else {
    // All bullets done (some skipped, some completed)
    onAllBulletsProcessed();  // Go to completion screen
  }
};
```

**User flow:**
- User clicks "Skip This Bullet"
- No API calls made
- Jump directly to next bullet's conversation (or completion screen if last bullet)
- This bullet will NOT have stored context for future use

---

### Screen 4: Review Extracted Facts

**Component:** `OnboardingFactsReview.tsx`

**What the user sees:**
```
┌──────────────────────────────────────────────────┐
│  Here's what I learned about this bullet:        │
│                                                  │
│  Bullet: Managed team of 5 engineers...          │
│                                                  │
│  📍 Situation:                                   │
│     Managing distributed team across time zones  │
│                                                  │
│  ⚡ Actions:                                      │
│     • Coordinated daily standups                 │
│     • Implemented async communication tools      │
│     • Mentored junior engineers                  │
│                                                  │
│  📊 Results:                                      │
│     • Delivered 3 major features on time         │
│     • Reduced bugs by 30%                        │
│                                                  │
│  🛠️ Skills: Leadership, Communication           │
│  💻 Tools: Jira, Slack, GitHub                   │
│  📅 Timeline: 6 months                           │
│                                                  │
│  Look good?                                      │
│  [  Edit Facts  ]  [  Looks Good, Save  ]        │
└──────────────────────────────────────────────────┘
```

**What happens:**

When screen loads, you already have `extracted_facts` from previous API call.

Display them nicely formatted.

**OPTION A:** User clicks "Looks Good, Save":
```typescript
// Call this API to save facts
const response = await fetch('http://localhost:8000/v2/context/confirm_facts', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: sessionId,
    facts: extractedFacts,  // from /v2/context/answer response
    user_confirmed: true
  })
});

const { bullet_id } = await response.json();
// Facts are now saved!

// Go to NEXT bullet (currentBulletIndex + 1)
// If more bullets remain, go back to Screen 3
// If all bullets done, go to Screen 5 (completion)
```

**OPTION B:** User clicks "Edit Facts":
- Make the facts fields editable
- User can modify text
- Then click "Save" → same API call as Option A

---

### Screen 5: Onboarding Complete

**Component:** `OnboardingComplete.tsx`

**What the user sees:**
```
┌─────────────────────────────────────┐
│  ✓ Onboarding Complete!             │
│                                     │
│  You added context to 8 bullets.    │
│                                     │
│  You're ready to start applying     │
│  for jobs!                          │
│                                     │
│  [  Go to Dashboard  ]              │
└─────────────────────────────────────┘
```

**What happens:**
- User clicks "Go to Dashboard"
- Navigate to main app (dashboard or job application page)

---

## The Complete Flow - Visual

```
User Journey:
┌─────────────┐
│  Screen 1   │  Upload resume DOCX
│   Upload    │  API: POST /upload → get bullets[]
└──────┬──────┘
       ↓
┌─────────────┐
│  Screen 2   │  Show all 8 bullets extracted
│   Preview   │  "Start Adding Context" button
└──────┬──────┘
       ↓
┌─────────────────────────────────────────────┐
│  Screen 3 - LOOP FOR EACH BULLET            │
│                                             │
│  For bullet #1:                             │
│    API: POST /v2/context/start              │
│    Show question, user answers              │
│    API: POST /v2/context/answer             │
│    If status='continue': ask more questions │
│    If status='complete': extracted_facts    │
│    ↓                                        │
│  Screen 4:                                  │
│    Show facts, user confirms                │
│    API: POST /v2/context/confirm_facts      │
│    ↓                                        │
│  Move to bullet #2, repeat...               │
│  Move to bullet #3, repeat...               │
│  ... until bullet #8 done                   │
└──────┬──────────────────────────────────────┘
       ↓
┌─────────────┐
│  Screen 5   │  "Onboarding Complete!"
│  Complete   │  Go to Dashboard
└─────────────┘
```

---

## State Management

You need to track:

```typescript
interface OnboardingState {
  // Which screen are we on?
  currentScreen: 'upload' | 'preview' | 'conversation' | 'review' | 'complete';

  // Resume data
  resumeFile: File | null;
  bullets: string[];

  // Which bullet are we working on?
  currentBulletIndex: number;  // 0 to bullets.length-1

  // Conversation for current bullet
  sessionId: string | null;
  conversationHistory: Array<{role: 'ai' | 'user', text: string}>;

  // Facts for current bullet
  extractedFacts: {
    situation: string;
    actions: string[];
    results: string[];
    skills: string[];
    tools: string[];
    timeline: string;
  } | null;

  // Completed bullets
  completedBulletIds: string[];  // bullet_ids from confirm_facts API
}
```

---

## Exact Components to Build

### 1. `OnboardingUpload.tsx`
```typescript
export default function OnboardingUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);

  const handleUpload = async () => {
    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', 'user123'); // Get from auth

    const res = await fetch('http://localhost:8000/upload', {
      method: 'POST',
      body: formData
    });

    const { bullets } = await res.json();

    // Pass bullets to parent and go to next screen
    onBulletsExtracted(bullets);
  };

  return (
    <div>
      <h1>Welcome to Resume Optimizer</h1>
      <p>Upload your resume to get started</p>

      <input
        type="file"
        accept=".docx"
        onChange={(e) => setFile(e.target.files[0])}
      />

      <button onClick={handleUpload} disabled={!file || loading}>
        {loading ? 'Uploading...' : 'Upload Resume'}
      </button>
    </div>
  );
}
```

### 2. `OnboardingBulletsPreview.tsx`
```typescript
interface Props {
  bullets: string[];
  onStartContext: () => void;
}

export default function OnboardingBulletsPreview({ bullets, onStartContext }: Props) {
  return (
    <div>
      <h1>Great! We found {bullets.length} bullets</h1>

      <ol>
        {bullets.map((bullet, idx) => (
          <li key={idx}>{bullet}</li>
        ))}
      </ol>

      <p>Next, I'll ask questions about each bullet.</p>

      <button onClick={onStartContext}>
        Start Adding Context
      </button>
    </div>
  );
}
```

### 3. `OnboardingConversation.tsx`
```typescript
interface Props {
  bulletText: string;
  bulletIndex: number;
  totalBullets: number;
  onComplete: (facts: any) => void;
  onSkipBullet: () => void;  // NEW: Allow skipping this bullet
}

export default function OnboardingConversation({
  bulletText,
  bulletIndex,
  totalBullets,
  onComplete,
  onSkipBullet
}: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [userAnswer, setUserAnswer] = useState('');
  const [conversation, setConversation] = useState<Array<{role: string, text: string}>>([]);
  const [loading, setLoading] = useState(false);

  // On mount: start context session
  useEffect(() => {
    startContextSession();
  }, [bulletText]);

  const startContextSession = async () => {
    const res = await fetch('http://localhost:8000/v2/context/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: 'user123',
        bullet_text: bulletText
      })
    });

    const { session_id, initial_question } = await res.json();
    setSessionId(session_id);
    setCurrentQuestion(initial_question);
    setConversation([{ role: 'ai', text: initial_question }]);
  };

  const handleSubmitAnswer = async () => {
    if (!userAnswer.trim()) return;

    // Add user's answer to conversation
    setConversation(prev => [...prev, { role: 'user', text: userAnswer }]);
    setLoading(true);

    const res = await fetch('http://localhost:8000/v2/context/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        user_answer: userAnswer
      })
    });

    const result = await res.json();
    setLoading(false);
    setUserAnswer('');

    if (result.status === 'continue') {
      // AI wants more questions
      setCurrentQuestion(result.next_question);
      setConversation(prev => [...prev, { role: 'ai', text: result.next_question }]);
    } else if (result.status === 'complete') {
      // Done! Show facts
      onComplete(result.extracted_facts);
    }
  };

  const handleSkipBullet = () => {
    // User doesn't want to add context for this bullet
    // Skip directly to next bullet
    onSkipBullet();
  };

  return (
    <div>
      <div>Progress: Bullet {bulletIndex + 1} of {totalBullets}</div>

      <div>
        <strong>Current Bullet:</strong>
        <p>{bulletText}</p>
      </div>

      <div>
        {conversation.map((msg, idx) => (
          <div key={idx}>
            <strong>{msg.role === 'ai' ? 'AI' : 'You'}:</strong> {msg.text}
          </div>
        ))}
      </div>

      <textarea
        value={userAnswer}
        onChange={(e) => setUserAnswer(e.target.value)}
        placeholder="Type your answer here..."
        rows={5}
      />

      <div style={{ marginTop: '10px' }}>
        <button onClick={handleSkipBullet} style={{ marginRight: '10px' }}>
          Skip This Bullet
        </button>
      </div>

      <div style={{ marginTop: '10px' }}>
        <button onClick={() => setUserAnswer('')} style={{ marginRight: '10px' }}>
          Skip Question
        </button>
        <button onClick={handleSubmitAnswer} disabled={loading}>
          {loading ? 'Submitting...' : 'Submit Answer'}
        </button>
      </div>
    </div>
  );
}
```

### 4. `OnboardingFactsReview.tsx`
```typescript
interface Props {
  bulletText: string;
  facts: any;
  sessionId: string;
  onSaved: (bulletId: string) => void;
}

export default function OnboardingFactsReview({
  bulletText,
  facts,
  sessionId,
  onSaved
}: Props) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedFacts, setEditedFacts] = useState(facts);

  const handleSave = async () => {
    const res = await fetch('http://localhost:8000/v2/context/confirm_facts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        facts: editedFacts,
        user_confirmed: true
      })
    });

    const { bullet_id } = await res.json();
    onSaved(bullet_id);
  };

  return (
    <div>
      <h2>Here's what I learned:</h2>

      <p><strong>Bullet:</strong> {bulletText}</p>

      {!isEditing ? (
        <div>
          <p><strong>Situation:</strong> {facts.situation}</p>
          <p><strong>Actions:</strong></p>
          <ul>
            {facts.actions?.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
          <p><strong>Results:</strong></p>
          <ul>
            {facts.results?.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <p><strong>Skills:</strong> {facts.skills?.join(', ')}</p>
          <p><strong>Tools:</strong> {facts.tools?.join(', ')}</p>
          <p><strong>Timeline:</strong> {facts.timeline}</p>
        </div>
      ) : (
        <div>
          {/* Editable fields */}
          <textarea
            value={editedFacts.situation}
            onChange={(e) => setEditedFacts({...editedFacts, situation: e.target.value})}
          />
          {/* ... other editable fields ... */}
        </div>
      )}

      {!isEditing && <button onClick={() => setIsEditing(true)}>Edit Facts</button>}
      <button onClick={handleSave}>Looks Good, Save</button>
    </div>
  );
}
```

### 5. `OnboardingComplete.tsx`
```typescript
interface Props {
  completedCount: number;
  totalBullets: number;
  onGoToDashboard: () => void;
}

export default function OnboardingComplete({ completedCount, totalBullets, onGoToDashboard }: Props) {
  const skippedCount = totalBullets - completedCount;

  return (
    <div>
      <h1>✓ Onboarding Complete!</h1>
      <p>You added context to {completedCount} of {totalBullets} bullets.</p>
      {skippedCount > 0 && (
        <p style={{ color: '#666' }}>
          {skippedCount} bullet{skippedCount > 1 ? 's' : ''} skipped.
          You can add context to them later from Settings.
        </p>
      )}
      <p>You're ready to start applying for jobs!</p>

      <button onClick={onGoToDashboard}>
        Go to Dashboard
      </button>
    </div>
  );
}
```

### 6. `OnboardingFlow.tsx` (Parent Container)
```typescript
export default function OnboardingFlow() {
  const [screen, setScreen] = useState<'upload' | 'preview' | 'conversation' | 'review' | 'complete'>('upload');
  const [bullets, setBullets] = useState<string[]>([]);
  const [currentBulletIndex, setCurrentBulletIndex] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [extractedFacts, setExtractedFacts] = useState(null);
  const [completedBulletIds, setCompletedBulletIds] = useState<string[]>([]);

  const handleBulletsExtracted = (extractedBullets: string[]) => {
    setBullets(extractedBullets);
    setScreen('preview');
  };

  const handleStartContext = () => {
    setCurrentBulletIndex(0);
    setScreen('conversation');
  };

  const handleConversationComplete = (facts: any) => {
    setExtractedFacts(facts);
    setScreen('review');
  };

  const handleSkipBullet = () => {
    // User skipped this bullet - move to next without saving facts
    const nextIndex = currentBulletIndex + 1;

    if (nextIndex < bullets.length) {
      // More bullets to process
      setCurrentBulletIndex(nextIndex);
      setExtractedFacts(null);
      setSessionId(null);
      setScreen('conversation');
    } else {
      // All bullets done (some skipped, some completed)
      setScreen('complete');
    }
  };

  const handleFactsSaved = (bulletId: string) => {
    setCompletedBulletIds(prev => [...prev, bulletId]);

    // Move to next bullet
    const nextIndex = currentBulletIndex + 1;

    if (nextIndex < bullets.length) {
      // More bullets to process
      setCurrentBulletIndex(nextIndex);
      setExtractedFacts(null);
      setSessionId(null);
      setScreen('conversation');
    } else {
      // All bullets done!
      setScreen('complete');
    }
  };

  return (
    <div>
      {screen === 'upload' && (
        <OnboardingUpload onBulletsExtracted={handleBulletsExtracted} />
      )}

      {screen === 'preview' && (
        <OnboardingBulletsPreview
          bullets={bullets}
          onStartContext={handleStartContext}
        />
      )}

      {screen === 'conversation' && (
        <OnboardingConversation
          bulletText={bullets[currentBulletIndex]}
          bulletIndex={currentBulletIndex}
          totalBullets={bullets.length}
          onComplete={handleConversationComplete}
          onSkipBullet={handleSkipBullet}
        />
      )}

      {screen === 'review' && (
        <OnboardingFactsReview
          bulletText={bullets[currentBulletIndex]}
          facts={extractedFacts}
          sessionId={sessionId}
          onSaved={handleFactsSaved}
        />
      )}

      {screen === 'complete' && (
        <OnboardingComplete
          completedCount={completedBulletIds.length}
          totalBullets={bullets.length}
          onGoToDashboard={() => window.location.href = '/dashboard'}
        />
      )}
    </div>
  );
}
```

---

## Checklist - Build These Exact Components

- [ ] `OnboardingUpload.tsx` - File upload, call POST /upload
- [ ] `OnboardingBulletsPreview.tsx` - Show extracted bullets list
- [ ] `OnboardingConversation.tsx` - Ask questions ONE BULLET AT A TIME
  - [ ] Call POST /v2/context/start when bullet starts
  - [ ] Call POST /v2/context/answer when user submits answer
  - [ ] Keep asking until status === 'complete'
- [ ] `OnboardingFactsReview.tsx` - Show extracted facts, allow editing
  - [ ] Call POST /v2/context/confirm_facts when user confirms
- [ ] `OnboardingComplete.tsx` - Success screen
- [ ] `OnboardingFlow.tsx` - Parent component that manages all 5 screens

---

## The Key Points

✅ **Upload resume** → Extract bullets
✅ **For EACH bullet** → Start conversation session
✅ **Ask questions** → Keep asking until AI says "complete"
✅ **Show facts** → User confirms
✅ **Move to next bullet** → Repeat until all done

**The loop is:**
```
For each bullet in bullets:
  1. POST /v2/context/start
  2. Show question
  3. User answers
  4. POST /v2/context/answer
  5. If continue: goto step 2
  6. If complete: show facts
  7. User confirms
  8. POST /v2/context/confirm_facts
  9. Move to next bullet
```

Build these 6 components exactly as shown above. The backend handles all AI logic. You just build the UI that calls the 3 APIs in the right order.
