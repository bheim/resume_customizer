# Build Complete Resume Optimizer App

## Overview

Build a full-stack resume optimizer web app where users:
1. **Sign up/Login** → Authenticate with Supabase
2. **Onboarding** → Upload resume, AI asks conversational questions about each bullet, store context
3. **Apply for Jobs** → Upload resume + job description, AI generates optimized resume using stored context
4. **Settings** → Manage saved bullets, update context with AI conversations, view profile

**Backend API is already running at `http://localhost:8000` (or environment variable `VITE_API_URL`).**
**Supabase is already configured for auth and database.**

Your job: Build the React frontend with all UI components, routing, and API integration.

---

## Tech Stack to Use

- **Frontend**: React + TypeScript + TailwindCSS
- **Auth**: Supabase Auth (email/password)
- **Routing**: React Router v6
- **State**: React Context API or Zustand
- **HTTP**: Axios or Fetch
- **UI Components**: shadcn/ui or your preferred component library
- **File Upload**: react-dropzone (optional)

---

## App Structure & Routes

```
/                          → Landing page (if not logged in)
/login                     → Login page
/signup                    → Signup page
/dashboard                 → Main dashboard (after login)
/onboarding                → First-time setup flow
/apply                     → Apply for a job (upload resume + JD)
/settings                  → Manage bullets and context
/settings/bullets          → View/edit all saved bullets
/settings/profile          → User profile
```

---

## Complete User Flows

### Flow 1: New User Signup & Onboarding

**Step 1: Signup**
- User enters email, password, name
- Call Supabase Auth signup
- Redirect to `/onboarding`

**Step 2: Onboarding - Upload Resume**
- Show: "Let's start by uploading your resume"
- User uploads DOCX file
- Call `POST /upload` → Get list of bullets
- Show preview of extracted bullets
- Button: "Continue to add context"

**Step 3: Onboarding - Conversational Context Gathering**
- For each bullet (or user can select which bullets):
  - Call `POST /v2/context/start` with the bullet
  - Show conversational dialog with AI questions
  - User answers 1-2 questions at a time
  - Call `POST /v2/context/answer` after each response
  - AI automatically decides when enough context gathered
  - Show extracted facts for user confirmation
  - Call `POST /v2/context/confirm_facts` to save

**Step 4: Onboarding Complete**
- Show success message: "Your resume is ready! You can now apply for jobs."
- Button: "Go to Dashboard"

### Flow 2: Applying for a Job (Ongoing Use)

**Step 1: Dashboard**
- Show welcome message
- Card: "Apply for a new job" → Button to `/apply`
- Show recent applications (if any)
- Show saved bullets count

**Step 2: Upload Resume + Job Description**
- User uploads resume DOCX
- User pastes job description (large textarea)
- Call `POST /upload` → Extract bullets
- Call `POST /v2/apply/match_bullets` → Match against stored bullets

**Step 3: Review Matched Bullets**
- Show table of bullets with matching status:
  - ✅ **Exact match** (confidence: 1.0) - "Using stored context automatically"
  - ✅ **High confidence** (0.9-1.0) - "Using stored context automatically"
  - ⚠️ **Medium confidence** (0.85-0.9) - "Is this the same as [stored bullet]?" with Yes/No buttons
  - ⚠️ **No match** (<0.85) - "Add context to improve this bullet" with "Add Context" button
- For unmatched bullets, user can click "Add Context" → Opens conversational Q&A
- Button: "Generate Optimized Resume"

**Step 4: Generate & Review**
- Call `POST /v2/apply/generate_with_facts`
- Show side-by-side comparison:
  - Left column: Original bullets
  - Right column: Enhanced bullets (with highlighting on changes)
- User can manually edit any enhanced bullet (inline editing)
- Button: "Download Resume"

**Step 5: Download**
- Call `POST /download` with final bullets
- Download DOCX file
- Show success message with option to apply for another job

### Flow 3: Settings & Bullet Management

**Settings Navigation:**
- My Bullets
- My Profile
- Account Settings

**My Bullets Page** (`/settings/bullets`)
- Show all saved bullets in a searchable table:
  - Bullet text (truncated if long, click to expand)
  - Date added
  - "Has context" badge (if facts exist)
  - Actions: "View Context" | "Update Context" | "Delete"

**View/Update Context:**
- Click "View Context" → Show extracted facts in a modal
- Show facts like:
  - Situation: "..."
  - Actions: [list]
  - Results: [list]
  - Skills: [list]
  - Tools: [list]
  - Timeline: "..."
- Button: "Add More Context" → Opens conversational Q&A
  - Call `POST /v2/context/start` with existing bullet_id
  - User can provide additional information
  - AI asks follow-up questions
  - Updates stored facts

**My Profile Page** (`/settings/profile`)
- Show user info: name, email
- Optional: Default resume settings (character limits, formatting preferences)
- Button: "Update Profile"

---

## Backend API Endpoints Reference

**Base URL**: `http://localhost:8000` (or `process.env.VITE_API_URL`)

### Authentication
Use **Supabase Auth SDK** - no custom backend endpoints needed:
```typescript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.VITE_SUPABASE_URL,
  process.env.VITE_SUPABASE_ANON_KEY
)

// Signup
await supabase.auth.signUp({ email, password })

// Login
await supabase.auth.signInWithPassword({ email, password })

// Get current user
const { data: { user } } = await supabase.auth.getUser()

// Logout
await supabase.auth.signOut()
```

### Resume & Bullet Operations

**1. Upload Resume & Extract Bullets**
```typescript
POST /upload
Content-Type: multipart/form-data

Request:
{
  file: File,  // DOCX
  user_id: string
}

Response:
{
  bullets: string[],
  message: string
}
```

**2. Match Bullets (for job applications)**
```typescript
POST /v2/apply/match_bullets
Content-Type: multipart/form-data

Request:
{
  user_id: string,
  resume_file: File  // DOCX
}

Response:
{
  matches: [
    {
      bullet_text: string,
      match_type: "exact" | "high" | "medium" | "no_match",
      confidence: number,
      matched_bullet_id?: string,
      matched_bullet_text?: string,
      has_facts: boolean
    }
  ]
}
```

**3. Generate Optimized Resume**
```typescript
POST /v2/apply/generate_with_facts
Content-Type: application/json

Request:
{
  user_id: string,
  job_description: string,
  bullets: [
    {
      bullet_text: string,
      bullet_id?: string,  // if matched
      use_stored_facts: boolean
    }
  ]
}

Response:
{
  enhanced_bullets: [
    {
      original: string,
      enhanced: string,
      used_facts: boolean
    }
  ]
}
```

**4. Download Resume DOCX**
```typescript
POST /download
Content-Type: multipart/form-data

Request:
{
  bullets: string,  // JSON.stringify(array)
  user_id: string
}

Response:
Binary DOCX file (trigger download in browser)
```

### Conversational Context Gathering

**5. Start Context Session**
```typescript
POST /v2/context/start
Content-Type: application/json

Request:
{
  user_id: string,
  bullet_text: string,
  bullet_id?: string  // if updating existing bullet
}

Response:
{
  session_id: string,
  bullet_id: string,
  initial_question: string,
  message: string
}
```

**6. Submit Answer & Get Next Question (or Complete)**
```typescript
POST /v2/context/answer
Content-Type: application/json

Request:
{
  session_id: string,
  user_answer: string
}

Response Option A - More questions needed:
{
  status: "continue",
  next_question: string,
  conversation_so_far: string
}

Response Option B - Done, ready to extract facts:
{
  status: "complete",
  extracted_facts: {
    situation: string,
    actions: string[],
    results: string[],
    skills: string[],
    tools: string[],
    timeline: string
  }
}
```

**7. Confirm & Save Facts**
```typescript
POST /v2/context/confirm_facts
Content-Type: application/json

Request:
{
  session_id: string,
  facts: {
    situation: string,
    actions: string[],
    results: string[],
    skills: string[],
    tools: string[],
    timeline: string
  },
  user_confirmed: boolean
}

Response:
{
  bullet_id: string,
  message: "Facts saved successfully"
}
```

### Legacy Endpoints (Optional - for backward compatibility)

**8. Start Traditional Q&A**
```typescript
POST /qa/start
Content-Type: application/json

Request:
{
  user_id: string,
  bullets: string[],
  job_description: string
}

Response:
{
  session_id: string,
  questions: [
    {
      question: string,
      type: string,
      bullet_index: number,
      bullet_text: string
    }
  ]
}
```

**9. Answer Traditional Q&A**
```typescript
POST /qa/answer
Content-Type: application/json

Request:
{
  session_id: string,
  answers: [
    {
      question: string,
      answer: string
    }
  ]
}

Response:
{
  status: "continue" | "complete",
  questions?: [...],  // if continue
  message: string
}
```

**10. Generate with Traditional Q&A**
```typescript
POST /generate
Content-Type: application/json

Request:
{
  user_id: string,
  bullets: string[],
  job_description: string,
  session_id: string
}

Response:
{
  enhanced_bullets: string[]
}
```

---

## Component Breakdown

### Auth Components

**`SignupPage`**
- Email, password, confirm password inputs
- "Sign Up" button → Supabase Auth signup
- Link to "Already have an account? Login"
- Show validation errors

**`LoginPage`**
- Email, password inputs
- "Login" button → Supabase Auth login
- Link to "Don't have an account? Sign Up"
- "Forgot password?" link
- Show validation errors

**`ProtectedRoute`**
- Wrapper component that checks if user is authenticated
- Redirect to `/login` if not authenticated
- Uses Supabase Auth state

### Onboarding Components

**`OnboardingFlow`**
- Multi-step wizard with progress indicator
- Steps: Upload → Add Context → Complete
- Uses stepper component (e.g., shadcn/ui Steps)

**`ResumeUploadStep`**
- Drag-and-drop file upload (react-dropzone)
- Accept only .docx files
- Show file name and size after selection
- "Extract Bullets" button
- Loading state during extraction
- Display extracted bullets as preview

**`AddContextStep`**
- Show one bullet at a time with context form
- Progress: "Bullet 2 of 8"
- Skip button: "I'll add context later"
- Next/Previous buttons
- Use `ConversationalDialog` component (see below)

**`OnboardingComplete`**
- Success message with checkmark animation
- Summary: "Added context to 5 of 8 bullets"
- "Go to Dashboard" button

### Job Application Components

**`JobApplicationPage`**
- Two-column layout:
  - Left: Upload resume + paste JD
  - Right: Preview/instructions
- "Upload Resume" dropzone
- "Job Description" large textarea (10+ rows)
- "Analyze & Match" button
- Goes to `BulletMatchingStep` after API call

**`BulletMatchingStep`**
- Table showing each bullet with:
  - Original bullet text
  - Match status badge (exact/high/medium/none)
  - Confidence score (if matched)
  - Action button based on status:
    - Exact/High: "✓ Using stored context" (disabled, green)
    - Medium: "Confirm Match?" button → Opens confirmation dialog
    - None: "Add Context" button → Opens `ConversationalDialog`
- Summary stats at top: "8 bullets matched, 2 need context"
- "Generate Resume" button at bottom (always available, but warn if no matches)

**`ConfirmMatchDialog`**
- Modal showing:
  - "Is this the same bullet?"
  - Current bullet text
  - Matched bullet text from database
  - Side-by-side comparison
  - "Yes, use stored context" button
  - "No, treat as new bullet" button

**`BulletComparisonStep`**
- Side-by-side view:
  - Left column: Original bullets (gray background)
  - Right column: Enhanced bullets (white background)
  - Highlight differences (e.g., added keywords in green)
- Each enhanced bullet is editable (inline textarea)
- Character count indicator (e.g., "145/150 chars")
- "Download Resume" button
- "Start Over" button

**`DownloadSuccess`**
- Success animation
- "Resume downloaded successfully!"
- Options:
  - "Apply for another job" → Back to `/apply`
  - "View my bullets" → Go to `/settings/bullets`
  - "Back to dashboard" → Go to `/dashboard`

### Settings Components

**`SettingsLayout`**
- Sidebar navigation:
  - My Bullets
  - My Profile
  - Account Settings
- Outlet for nested routes

**`BulletsListPage`**
- Search bar (filter bullets by text)
- Sort options: "Date added", "Has context", "Most used"
- Table with columns:
  - Bullet Text (truncated, click to expand)
  - Context Status (badge: "Has context" or "No context")
  - Date Added
  - Actions (View, Edit, Delete dropdown)
- Pagination if > 20 bullets
- "Add New Bullet Manually" button (optional)

**`BulletContextModal`**
- Shows when clicking "View Context" on a bullet
- Display facts in organized sections:
  - **Situation**: [text]
  - **Actions**: [bullet list]
  - **Results**: [bullet list]
  - **Skills**: [pills/tags]
  - **Tools**: [pills/tags]
  - **Timeline**: [text]
- Buttons:
  - "Edit Facts" → Make fields editable, save changes
  - "Add More Context" → Opens `ConversationalDialog`
  - "Close"

**`ProfilePage`**
- User info display
- Editable fields: name, email (email change triggers Supabase flow)
- "Update Profile" button
- "Change Password" button → Opens change password dialog
- "Delete Account" button (with confirmation)

### Shared Components

**`ConversationalDialog`**
```typescript
interface ConversationalDialogProps {
  bulletText: string;
  existingBulletId?: string;
  onComplete: (facts: ExtractedFacts) => void;
  onCancel: () => void;
}
```

**UI:**
- Modal/dialog overlay
- Title: "Let's add context to your bullet"
- Show the bullet text in a highlighted box
- Conversational messages displayed as chat:
  - AI questions on left (with AI avatar)
  - User answers on right (with user avatar)
- Large textarea for user to type answer
- "Skip this question" button (light gray)
- "Submit" button (primary color)
- Progress indicator: "Gathering context..." with spinner

**Behavior:**
1. On mount, call `POST /v2/context/start`
2. Display `initial_question`
3. User types answer and clicks "Submit"
4. Call `POST /v2/context/answer` with answer
5. If `status: "continue"`:
   - Display `next_question` in chat
   - Repeat steps 3-5
6. If `status: "complete"`:
   - Show `extracted_facts` for user review
   - "Looks good!" button → Call `POST /v2/context/confirm_facts` → `onComplete()`
   - "Edit" button → Make facts editable before confirming

**`LoadingSpinner`**
- Reusable spinner component for API calls
- Show during: file upload, API requests, resume generation

**`ErrorAlert`**
- Reusable error display component
- Show API errors with retry button
- Dismissible

---

## State Management

### User Context
```typescript
interface UserContextType {
  user: User | null;
  loading: boolean;
  signUp: (email: string, password: string) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}
```

### Application State (consider Zustand)
```typescript
interface AppState {
  // Onboarding
  onboardingBullets: string[];
  onboardingProgress: number;

  // Job Application
  currentJobDescription: string;
  extractedBullets: string[];
  matchedBullets: BulletMatch[];
  enhancedBullets: EnhancedBullet[];

  // Settings
  savedBullets: SavedBullet[];

  // Actions
  setOnboardingBullets: (bullets: string[]) => void;
  setMatchedBullets: (matches: BulletMatch[]) => void;
  // ... etc
}
```

---

## Key UX Principles

### 🎯 Conversational, Not Formal
- Questions feel like a friendly career coach, not a form
- Use warm, encouraging language
- Example: "Tell me more about the impact this had!" instead of "Describe quantifiable outcomes."

### 🚀 Progressive Disclosure
- Don't show all 8 bullets' questions at once
- One bullet at a time during onboarding
- 1-2 questions at a time in the conversational dialog
- Clear progress indicators

### ✅ User Control & Flexibility
- Always allow skipping questions
- Let users skip bullets during onboarding ("I'll add context later")
- Can add context later from Settings
- Can manually edit enhanced bullets before downloading

### 🔍 Transparency
- Always show what's happening: "Analyzing resume...", "Generating enhanced bullets..."
- Show match confidence scores
- Show before/after comparison
- Explain why certain bullets matched

### 🎨 Visual Clarity
- Use badges/pills for status (has context, no context, matched, etc.)
- Color coding: Green = good/matched, Yellow = needs attention, Gray = neutral
- Highlight changes in enhanced bullets
- Use icons for actions (edit, delete, download, etc.)

### ⚡ Performance
- Show loading states immediately
- Optimistic UI updates where possible
- Cache user's bullets in state to avoid re-fetching
- Debounce search inputs

---

## File Structure

```
src/
├── components/
│   ├── auth/
│   │   ├── LoginPage.tsx
│   │   ├── SignupPage.tsx
│   │   └── ProtectedRoute.tsx
│   ├── onboarding/
│   │   ├── OnboardingFlow.tsx
│   │   ├── ResumeUploadStep.tsx
│   │   ├── AddContextStep.tsx
│   │   └── OnboardingComplete.tsx
│   ├── apply/
│   │   ├── JobApplicationPage.tsx
│   │   ├── BulletMatchingStep.tsx
│   │   ├── ConfirmMatchDialog.tsx
│   │   ├── BulletComparisonStep.tsx
│   │   └── DownloadSuccess.tsx
│   ├── settings/
│   │   ├── SettingsLayout.tsx
│   │   ├── BulletsListPage.tsx
│   │   ├── BulletContextModal.tsx
│   │   └── ProfilePage.tsx
│   ├── shared/
│   │   ├── ConversationalDialog.tsx
│   │   ├── LoadingSpinner.tsx
│   │   ├── ErrorAlert.tsx
│   │   └── Navbar.tsx
│   └── dashboard/
│       └── Dashboard.tsx
├── contexts/
│   ├── UserContext.tsx
│   └── AppStateContext.tsx (or use Zustand store)
├── lib/
│   ├── supabase.ts          // Supabase client
│   └── api.ts               // API functions for backend
├── types/
│   └── index.ts             // TypeScript interfaces
├── App.tsx
└── main.tsx
```

---

## API Helper Functions (Example)

Create a `/src/lib/api.ts` file with helper functions:

```typescript
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Upload resume
export async function uploadResume(file: File, userId: string) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('user_id', userId);

  const response = await fetch(`${API_URL}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error('Failed to upload resume');
  return response.json();
}

// Start context session
export async function startContextSession(userId: string, bulletText: string, bulletId?: string) {
  const response = await fetch(`${API_URL}/v2/context/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, bullet_text: bulletText, bullet_id: bulletId }),
  });

  if (!response.ok) throw new Error('Failed to start context session');
  return response.json();
}

// Submit context answer
export async function submitContextAnswer(sessionId: string, answer: string) {
  const response = await fetch(`${API_URL}/v2/context/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, user_answer: answer }),
  });

  if (!response.ok) throw new Error('Failed to submit answer');
  return response.json();
}

// Confirm facts
export async function confirmFacts(sessionId: string, facts: any, confirmed: boolean) {
  const response = await fetch(`${API_URL}/v2/context/confirm_facts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, facts, user_confirmed: confirmed }),
  });

  if (!response.ok) throw new Error('Failed to confirm facts');
  return response.json();
}

// Match bullets
export async function matchBullets(userId: string, resumeFile: File) {
  const formData = new FormData();
  formData.append('user_id', userId);
  formData.append('resume_file', resumeFile);

  const response = await fetch(`${API_URL}/v2/apply/match_bullets`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error('Failed to match bullets');
  return response.json();
}

// Generate with facts
export async function generateWithFacts(userId: string, jobDescription: string, bullets: any[]) {
  const response = await fetch(`${API_URL}/v2/apply/generate_with_facts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, job_description: jobDescription, bullets }),
  });

  if (!response.ok) throw new Error('Failed to generate resume');
  return response.json();
}

// Download resume
export async function downloadResume(bullets: string[], userId: string) {
  const formData = new FormData();
  formData.append('bullets', JSON.stringify(bullets));
  formData.append('user_id', userId);

  const response = await fetch(`${API_URL}/download`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error('Failed to download resume');

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'optimized_resume.docx';
  a.click();
  window.URL.revokeObjectURL(url);
}
```

---

## Environment Variables

Create `.env` file:
```
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=<your-supabase-url>
VITE_SUPABASE_ANON_KEY=<your-supabase-anon-key>
```

---

## Implementation Checklist

### Phase 1: Auth & Routing ✓
- [ ] Set up React Router with routes
- [ ] Create Supabase client
- [ ] Build Login/Signup pages
- [ ] Build ProtectedRoute wrapper
- [ ] Create UserContext for auth state
- [ ] Add logout functionality

### Phase 2: Onboarding ✓
- [ ] Build OnboardingFlow with stepper
- [ ] Build ResumeUploadStep with file upload
- [ ] Build ConversationalDialog component
- [ ] Integrate /upload API
- [ ] Integrate /v2/context/* APIs
- [ ] Build AddContextStep
- [ ] Build OnboardingComplete screen

### Phase 3: Dashboard ✓
- [ ] Build Dashboard layout
- [ ] Show welcome message
- [ ] Show quick stats (bullets saved, contexts added)
- [ ] Add navigation to Apply/Settings

### Phase 4: Job Application ✓
- [ ] Build JobApplicationPage (upload + JD input)
- [ ] Integrate /v2/apply/match_bullets API
- [ ] Build BulletMatchingStep with table
- [ ] Build ConfirmMatchDialog
- [ ] Integrate /v2/apply/generate_with_facts API
- [ ] Build BulletComparisonStep (side-by-side)
- [ ] Integrate /download API
- [ ] Build DownloadSuccess screen

### Phase 5: Settings ✓
- [ ] Build SettingsLayout with sidebar
- [ ] Build BulletsListPage with search/sort
- [ ] Build BulletContextModal
- [ ] Allow editing facts
- [ ] Allow adding more context to existing bullets
- [ ] Build ProfilePage
- [ ] Add delete bullet functionality

### Phase 6: Polish ✓
- [ ] Add loading states everywhere
- [ ] Add error handling and error messages
- [ ] Add success notifications (toast/snackbar)
- [ ] Make responsive for mobile
- [ ] Add animations (page transitions, success states)
- [ ] Add empty states ("No bullets yet")
- [ ] Add keyboard shortcuts (ESC to close modals, etc.)

---

## Important Notes

### ✅ DO Build:
- All React components and pages
- Routing and navigation
- Supabase Auth integration
- API calls to backend endpoints
- Loading and error states
- Responsive UI
- Form validations

### ❌ DO NOT Build:
- Backend API endpoints (already done)
- Database schemas (already done)
- AI/LLM logic (backend handles this)
- Resume parsing logic (backend handles this)
- DOCX generation (backend handles this)

---

## Success Criteria

When you're done, a user should be able to:
1. ✅ Sign up and login with email/password
2. ✅ Upload their resume and see extracted bullets
3. ✅ Have conversational Q&A with AI about each bullet
4. ✅ See extracted facts and confirm/edit them
5. ✅ Apply for a job by uploading resume + JD
6. ✅ See which bullets matched their stored bullets
7. ✅ Get an optimized resume using stored context
8. ✅ Download the enhanced resume as DOCX
9. ✅ View all saved bullets in Settings
10. ✅ Update context for any bullet at any time

---

## That's Everything!

Focus on building a polished, intuitive UI that makes the conversational Q&A feel natural. The magic is in the UX: make users feel like they're talking to a career coach, not filling out a form.

The backend handles all the AI, matching, and file processing. You just need to build beautiful React components that call these endpoints and provide a delightful user experience.

Good luck! 🚀
