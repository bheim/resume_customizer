# Lovable Prompt: Dual-Mode Resume Optimizer Frontend

## Overview

Build a resume optimization app with TWO modes:
1. **Quick Keyword Boost** - Fast ATS optimization (10-30 seconds, no questions)
2. **Full Optimization** - Best results with context gathering (2-5 minutes, asks questions)

Both modes use the same backend API with different endpoints.

---

## User Flow

### Landing Page
1. User uploads resume (DOCX)
2. User pastes job description
3. User chooses optimization mode:
   - **Quick Keyword Boost** (recommended for speed)
   - **Full Optimization** (recommended for best results)
4. Click "Optimize Resume"

### Quick Mode (Keyword-Only)
```
Upload → Process → Wait ~20 seconds → Download optimized resume
```

### Full Mode (With Facts)
```
Upload → Bullet Matching → Optimization → Download
```

### Both modes end at:
- Results page showing before/after scores
- Download button for optimized DOCX

---

## API Endpoints to Use

### Base URL
```
const API_BASE = "http://localhost:8000";  // Update for production
```

### Endpoint 1: Match Bullets (Both Modes)
```typescript
POST /v2/apply/match_bullets
Content-Type: multipart/form-data

FormData:
  user_id: string
  resume_file?: File (optional if base resume exists)

Response:
{
  session_id: string,
  bullets: string[],
  matches: Array<{
    bullet_index: number,
    bullet_text: string,
    bullet_id: string | null,
    has_facts: boolean,
    facts: object | null
  }>
}
```

### Endpoint 2a: Generate Keywords Only (Quick Mode)
```typescript
POST /v2/apply/generate_keywords_only
Content-Type: application/json

Body:
{
  user_id: string,
  job_description: string,
  bullets: Array<{
    bullet_text: string
  }>
}

Response:
{
  enhanced_bullets: Array<{
    original: string,
    enhanced: string,
    used_facts: boolean
  }>,
  scores: {
    before_score: number,
    after_score: number,
    improvement: number,
    dimensions: {
      before: { relevance: number, ... },
      after: { relevance: number, ... }
    }
  },
  optimization_mode: "keywords_only"
}
```

### Endpoint 2b: Generate with Facts (Full Mode)
```typescript
POST /v2/apply/generate_with_facts
Content-Type: application/json

Body:
{
  user_id: string,
  job_description: string,
  bullets: Array<{
    bullet_text: string,
    bullet_id?: string,
    use_stored_facts: boolean
  }>
}

Response:
{
  enhanced_bullets: Array<{
    original: string,
    enhanced: string,
    used_facts: boolean
  }>,
  scores: {
    before_score: number,
    after_score: number,
    improvement: number,
    dimensions: object
  }
}
```

### Endpoint 3: Download (Both Modes)
```typescript
POST /download
Content-Type: multipart/form-data

FormData:
  bullets: string (JSON array of enhanced_bullets)
  user_id: string
  session_id: string
  file?: File (optional)

Response:
  DOCX file download
  Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

---

## Component Structure

### 1. Landing Page (`/`)
- Hero section: "Optimize Your Resume for Any Job"
- Two large cards side-by-side:

**Card 1: Quick Keyword Boost ⚡**
```
"Fast ATS Optimization"

✅ Ready in seconds
✅ No questions needed
✅ Smart keyword alignment
✅ +2-5 point improvement

Perfect for: Last-minute applications, multiple jobs, quick updates

[Choose Quick Mode →]
```

**Card 2: Full Optimization 🎯**
```
"Best Possible Resume"

✅ Answer 5-10 questions
✅ Uses your stored experience
✅ Maximum optimization
✅ +10-20 point improvement

Perfect for: Dream jobs, career changes, thorough optimization

[Choose Full Mode →]
```

### 2. Upload Page (`/upload`)
- File upload dropzone (accept DOCX only)
- Textarea for job description (large, placeholder: "Paste the full job description here...")
- Validate:
  - Resume has bullets (show error if none found)
  - Job description is not empty
- Show selected mode at top
- Button: "Optimize Resume" (disabled until valid)
- Link: "Change Mode"

### 3. Processing Page (`/processing`)

**Quick Mode:**
```tsx
<div className="text-center">
  <Spinner />
  <h2>Optimizing your resume...</h2>
  <p>This should take 10-30 seconds</p>
  <ProgressBar current={currentBullet} total={totalBullets} />
</div>
```

**Full Mode:**
```tsx
<div className="text-center">
  <Spinner />
  <h2>Analyzing your resume...</h2>
  <p>Matching bullets to your experience library</p>
  <ProgressBar current={currentBullet} total={totalBullets} />
</div>
```

### 4. Results Page (`/results`)
- Top section: Score comparison
  ```
  Before: [67.5] ───────────────────────→ After: [84.0]
                   +16.5 points ✨
  ```
- Expandable sections for each dimension:
  - Relevance: before → after
  - Specificity: before → after
  - Language: before → after
  - ATS Optimization: before → after
- Bullet-by-bullet comparison (expandable):
  ```
  Bullet 1:
    Before: "Developed pricing analytics framework..."
    After:  "Developed pricing analytics framework to drive strategic insights..."
    ✓ Keyword-optimized
  ```
- Large download button: "Download Optimized Resume"
- Secondary actions:
  - "Optimize Another Resume"
  - "Try Different Mode"

---

## State Management

### Global State
```typescript
interface AppState {
  mode: 'quick' | 'full';
  userId: string;
  sessionId?: string;
  resumeFile?: File;
  jobDescription: string;
  bullets: string[];
  matches?: BulletMatch[];
  enhancedBullets?: EnhancedBullet[];
  scores?: Scores;
  loading: boolean;
  error?: string;
}
```

### API Call Flow

**Quick Mode:**
```typescript
async function runQuickOptimization() {
  setLoading(true);

  try {
    // Step 1: Match bullets (get session_id)
    const matchFormData = new FormData();
    matchFormData.append('user_id', userId);
    matchFormData.append('resume_file', resumeFile);

    const matchRes = await fetch(`${API_BASE}/v2/apply/match_bullets`, {
      method: 'POST',
      body: matchFormData
    });
    const { session_id, bullets } = await matchRes.json();

    setSessionId(session_id);
    setBullets(bullets);

    // Step 2: Generate keywords only
    const generateRes = await fetch(`${API_BASE}/v2/apply/generate_keywords_only`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        job_description: jobDescription,
        bullets: bullets.map(text => ({ bullet_text: text }))
      })
    });
    const { enhanced_bullets, scores } = await generateRes.json();

    setEnhancedBullets(enhanced_bullets);
    setScores(scores);
    setLoading(false);

    // Navigate to results
    navigate('/results');

  } catch (error) {
    setError(error.message);
    setLoading(false);
  }
}
```

**Full Mode:**
```typescript
async function runFullOptimization() {
  setLoading(true);

  try {
    // Step 1: Match bullets
    const matchFormData = new FormData();
    matchFormData.append('user_id', userId);
    matchFormData.append('resume_file', resumeFile);

    const matchRes = await fetch(`${API_BASE}/v2/apply/match_bullets`, {
      method: 'POST',
      body: matchFormData
    });
    const { session_id, bullets, matches } = await matchRes.json();

    setSessionId(session_id);
    setBullets(bullets);
    setMatches(matches);

    // Step 2: Generate with facts
    const generateRes = await fetch(`${API_BASE}/v2/apply/generate_with_facts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        job_description: jobDescription,
        bullets: bullets.map((text, idx) => ({
          bullet_text: text,
          bullet_id: matches[idx].bullet_id,
          use_stored_facts: matches[idx].has_facts
        }))
      })
    });
    const { enhanced_bullets, scores } = await generateRes.json();

    setEnhancedBullets(enhanced_bullets);
    setScores(scores);
    setLoading(false);

    // Navigate to results
    navigate('/results');

  } catch (error) {
    setError(error.message);
    setLoading(false);
  }
}
```

**Download:**
```typescript
async function downloadResume() {
  const formData = new FormData();
  formData.append('bullets', JSON.stringify(enhancedBullets));
  formData.append('user_id', userId);
  formData.append('session_id', sessionId);
  // Don't append file - it will use the session resume

  const response = await fetch(`${API_BASE}/download`, {
    method: 'POST',
    body: formData
  });

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'resume_optimized.docx';
  a.click();
  window.URL.revokeObjectURL(url);
}
```

---

## Styling Guidelines

### Colors
- Primary: Blue (#3B82F6) for Quick Mode
- Secondary: Purple (#8B5CF6) for Full Mode
- Success: Green (#10B981) for improvements
- Neutral: Gray for text

### Typography
- Headings: Bold, large (text-2xl, text-3xl)
- Body: Regular (text-base)
- Scores: Extra large (text-5xl) for impact

### Layout
- Max width: 1200px
- Padding: generous (p-8)
- Cards: rounded corners (rounded-lg), shadow (shadow-lg)
- Spacing: consistent (gap-6, space-y-4)

### Animations
- Score reveal: Count up from before to after
- Progress bar: Smooth width transition
- Button hover: Scale slightly (scale-105)

---

## Error Handling

### Common Errors
```typescript
const ERROR_MESSAGES = {
  'no_bullets_found': 'No bullets found in resume. Please ensure your resume uses bullet points.',
  'empty_or_small_file': 'Resume file is too small or empty.',
  'bad_docx': 'Invalid DOCX file. Please upload a valid Microsoft Word document.',
  'bullet_count_mismatch': 'Internal error: bullet count mismatch.',
  'session_not_found': 'Session expired. Please start over.',
  'supabase_not_configured': 'Database not configured. Please contact support.'
};

function handleError(errorCode: string) {
  const message = ERROR_MESSAGES[errorCode] || 'An unexpected error occurred.';
  toast.error(message);
}
```

### Retry Logic
- On timeout: Show "This is taking longer than expected. Hang tight!"
- On server error: Show "Something went wrong. Please try again."
- Retry button should restart from upload page

---

## Responsive Design

### Mobile (<768px)
- Stack mode cards vertically
- Reduce padding and font sizes
- Make score chart more compact
- Scrollable bullet comparisons

### Tablet (768px - 1024px)
- Side-by-side mode cards (if space allows)
- Medium padding
- Readable font sizes

### Desktop (>1024px)
- Full layout as described above
- Maximum width of 1200px
- Centered content

---

## Performance Optimizations

1. **Lazy load results:** Don't fetch/render bullets until results page
2. **Streaming uploads:** Use multipart upload for large files
3. **Debounce job description:** Don't validate on every keystroke
4. **Cache session_id:** Store in localStorage to resume if user refreshes
5. **Preload next page:** Start loading results page assets while processing

---

## Accessibility

- ✅ Keyboard navigation (Tab, Enter, Escape)
- ✅ ARIA labels for all interactive elements
- ✅ Screen reader announcements for loading states
- ✅ Focus indicators on all focusable elements
- ✅ Alt text for icons
- ✅ Semantic HTML (main, section, article, etc.)

---

## Testing Checklist

### Quick Mode
- [ ] Upload resume → Get session_id
- [ ] Generate keywords → Get enhanced bullets
- [ ] Download → Get DOCX file
- [ ] Scores display correctly
- [ ] No errors in console

### Full Mode
- [ ] Upload resume → Get session_id and matches
- [ ] Generate with facts → Get enhanced bullets
- [ ] Download → Get DOCX file
- [ ] Scores display correctly
- [ ] No errors in console

### Edge Cases
- [ ] Empty job description → Show error
- [ ] No bullets in resume → Show error
- [ ] Very long job description (10,000+ chars) → Works
- [ ] Many bullets (20+) → Works, shows progress
- [ ] Network error → Shows friendly error message
- [ ] Timeout → Shows "taking longer" message

---

## Example User Journey

### Quick Mode Success Path
```
1. User lands on homepage
2. Sees two cards, clicks "Choose Quick Mode"
3. Uploads "MyResume.docx" (validates, shows ✓)
4. Pastes job description from LinkedIn
5. Clicks "Optimize Resume"
6. Sees "Optimizing your resume... 3/8 bullets processed"
7. After 18 seconds, redirected to results
8. Sees "+4.2 point improvement" with before/after scores
9. Clicks "Download Optimized Resume"
10. Downloads "resume_optimized.docx"
11. Success! Resume is ATS-optimized.
```

### Full Mode Success Path
```
1. User lands on homepage
2. Sees two cards, clicks "Choose Full Mode"
3. Uploads resume, pastes job description
4. Clicks "Optimize Resume"
5. Sees "Matching bullets to your experience library..."
6. Sees "3 bullets matched with facts, 5 without"
7. Proceeds to generation
8. After 3 minutes, sees results
9. Sees "+18.5 point improvement" with dimensions breakdown
10. Downloads optimized resume
11. Success!
```

---

## Implementation Tips

1. Use **React Query** or **SWR** for API calls (built-in caching, error handling)
2. Use **React Hook Form** for upload page validation
3. Use **Framer Motion** for animations (score reveal, progress bar)
4. Use **react-hot-toast** for error/success notifications
5. Use **Zustand** or **Context API** for state management
6. Use **TailwindCSS** for styling

---

## Additional Features (Nice to Have)

1. **Email results:** Send optimized resume to user's email
2. **Save to cloud:** Store session for later retrieval
3. **Compare modes:** Side-by-side comparison of quick vs full
4. **Resume history:** Show past optimizations
5. **A/B test messaging:** Track which mode users prefer

---

## Success Metrics to Track

1. **Mode preference:** % choosing Quick vs Full
2. **Completion rate:** % who download after optimization
3. **Satisfaction:** Average improvement score
4. **Time to download:** Median time from upload to download
5. **Error rate:** % of sessions with errors

---

## Final Notes

- The backend is **already fully implemented** and tested
- You only need to build the **frontend UI** as specified above
- Both modes use the **same download endpoint** for simplicity
- The API returns the **same response format** for both modes (just different optimization quality)
- Focus on making the **mode selection clear** and the **results compelling**

Good luck building! 🚀
