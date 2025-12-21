# Add Keyword-Only Mode to Existing Resume Optimizer

## Context
The full optimization flow is **already working**:
- ✅ Upload resume works
- ✅ Match bullets works
- ✅ Generate with facts works
- ✅ Download optimized resume works
- ✅ Results display works

## What Needs to Be Added

Add a **mode selector** so users can choose between:
1. **Full Optimization** (existing flow - uses `/v2/apply/generate_with_facts`)
2. **Keyword-Only Optimization** (new flow - uses `/v2/apply/generate_keywords_only`)

---

## Step 1: Add Mode Selector UI

**Where:** On the page where the user clicks "Optimize Resume" (after uploading resume and pasting job description)

**Add this UI element** above the "Optimize Resume" button:

```tsx
// Mode selector - radio buttons or toggle
<div className="mb-6">
  <label className="block text-sm font-medium mb-3">
    Optimization Mode
  </label>

  <div className="space-y-3">
    {/* Full Optimization */}
    <div
      className={`p-4 border rounded-lg cursor-pointer ${
        mode === 'full' ? 'border-purple-500 bg-purple-50' : 'border-gray-300'
      }`}
      onClick={() => setMode('full')}
    >
      <div className="flex items-start">
        <input
          type="radio"
          checked={mode === 'full'}
          onChange={() => setMode('full')}
          className="mt-1 mr-3"
        />
        <div>
          <div className="font-semibold">Full Optimization 🎯</div>
          <div className="text-sm text-gray-600">
            Best results with your stored experience (+10-20 point improvement)
          </div>
        </div>
      </div>
    </div>

    {/* Keyword-Only */}
    <div
      className={`p-4 border rounded-lg cursor-pointer ${
        mode === 'keywords' ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
      }`}
      onClick={() => setMode('keywords')}
    >
      <div className="flex items-start">
        <input
          type="radio"
          checked={mode === 'keywords'}
          onChange={() => setMode('keywords')}
          className="mt-1 mr-3"
        />
        <div>
          <div className="font-semibold">Quick Keyword Boost ⚡</div>
          <div className="text-sm text-gray-600">
            Fast ATS optimization, no questions needed (~30 seconds, +2-5 point improvement)
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

---

## Step 2: Modify the Optimization Logic

**Find the existing code** that calls `/v2/apply/generate_with_facts` and wrap it in a conditional.

### Current Code (approximately):
```typescript
// Existing full optimization call
const response = await fetch('/v2/apply/generate_with_facts', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_id: userId,
    job_description: jobDescription,
    bullets: bullets.map((text, idx) => ({
      bullet_text: text,
      bullet_id: matches[idx]?.bullet_id,
      use_stored_facts: matches[idx]?.has_facts
    }))
  })
});
```

### Updated Code (with mode selector):
```typescript
// Choose endpoint based on mode
const endpoint = mode === 'keywords'
  ? '/v2/apply/generate_keywords_only'
  : '/v2/apply/generate_with_facts';

// Prepare request body based on mode
const requestBody = mode === 'keywords'
  ? {
      // Keyword-only: simpler format (no bullet_id or use_stored_facts needed)
      user_id: userId,
      job_description: jobDescription,
      bullets: bullets.map(text => ({
        bullet_text: text
      }))
    }
  : {
      // Full optimization: existing format
      user_id: userId,
      job_description: jobDescription,
      bullets: bullets.map((text, idx) => ({
        bullet_text: text,
        bullet_id: matches[idx]?.bullet_id,
        use_stored_facts: matches[idx]?.has_facts
      }))
    };

// Make the API call
const response = await fetch(endpoint, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(requestBody)
});

const { enhanced_bullets, scores } = await response.json();

// Everything after this stays the same - both endpoints return the same format!
```

---

## Step 3: Add State for Mode

**Add to your component state:**

```typescript
const [mode, setMode] = useState<'full' | 'keywords'>('full');
```

That's it! Default to 'full' to maintain existing behavior.

---

## Important Notes

### ✅ No Changes Needed To:
- Upload flow (stays the same)
- Match bullets endpoint (stays the same - both modes use it to get session_id)
- Download endpoint (stays the same - both modes return `enhanced_bullets` in same format)
- Results display (stays the same - both modes return `scores` object)
- Error handling (stays the same)

### ✅ Both Endpoints Return Same Format:
```typescript
{
  enhanced_bullets: Array<{
    original: string,
    enhanced: string,
    used_facts: boolean  // true for full mode, false for keyword mode
  }>,
  scores: {
    before_score: number,
    after_score: number,
    improvement: number,
    dimensions: {...}
  }
}
```

### ⚡ The Only Difference:
- **Full mode:** Uses matched bullet IDs and facts from database
- **Keyword mode:** Just passes bullet text, no IDs or facts needed

---

## Quick Reference: API Endpoints

### Keyword-Only (NEW)
```http
POST /v2/apply/generate_keywords_only
Content-Type: application/json

{
  "user_id": "string",
  "job_description": "string",
  "bullets": [
    {"bullet_text": "string"}
  ]
}
```

### Full Optimization (EXISTING - unchanged)
```http
POST /v2/apply/generate_with_facts
Content-Type: application/json

{
  "user_id": "string",
  "job_description": "string",
  "bullets": [
    {
      "bullet_text": "string",
      "bullet_id": "string",
      "use_stored_facts": boolean
    }
  ]
}
```

---

## Expected User Experience

### Before (existing):
```
1. Upload resume
2. Paste job description
3. Click "Optimize Resume"
4. Wait for optimization
5. Download result
```

### After (with mode selector):
```
1. Upload resume
2. Paste job description
3. Choose mode: [○ Full Optimization] [● Quick Keyword Boost]  ← NEW
4. Click "Optimize Resume"
5. Wait for optimization
6. Download result
```

---

## Testing

After implementing:

1. **Test Full Mode** (should work exactly as before):
   - Select "Full Optimization"
   - Click optimize
   - Verify it calls `/v2/apply/generate_with_facts`
   - Verify results display correctly

2. **Test Keyword Mode** (new):
   - Select "Quick Keyword Boost"
   - Click optimize
   - Verify it calls `/v2/apply/generate_keywords_only`
   - Verify results display correctly (faster, smaller improvement)

3. **Test Mode Switching**:
   - Switch between modes before clicking optimize
   - Verify selection persists correctly

---

## Optional Enhancement

If you want to show different loading messages based on mode:

```typescript
const loadingMessage = mode === 'keywords'
  ? 'Optimizing keywords... (~30 seconds)'
  : 'Optimizing with your stored experience... (2-5 minutes)';
```

---

## Summary

**What you're adding:**
1. Radio button / toggle to select optimization mode (2 options)
2. Conditional logic: if keyword mode, call different endpoint with simpler payload
3. Everything else stays exactly the same

**Lines of code to change:** ~20-30 lines total

**Files to modify:** Probably just 1 file (the optimization page component)

That's it! The backend handles the rest.
