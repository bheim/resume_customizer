# Resume Optimizer API - Frontend Integration Guide

## Overview

The backend now supports **two optimization modes**:

1. **Full Optimization (with facts)** - Asks questions, gathers context, generates with stored facts
2. **Keyword-Only Optimization** - Fast ATS keyword alignment without questions

---

## Two Optimization Flows

### Flow 1: Full Optimization (Existing - with Facts)

**Use this when:** User wants the best possible resume with detailed context gathering.

**Steps:**
```
1. POST /v2/apply/match_bullets
   → Upload resume (or use base resume)
   → Returns bullets matched to stored facts

2. POST /v2/apply/generate_with_facts
   → Send bullets + job description
   → Uses stored facts OR optimizes without facts
   → Returns enhanced bullets with scores

3. POST /download
   → Send enhanced bullets + user_id + session_id
   → Returns optimized DOCX file
```

**Endpoint Details:**

#### 1. Match Bullets
```http
POST /v2/apply/match_bullets
Content-Type: multipart/form-data

user_id: string (required)
resume_file: file (optional - uses base resume if not provided)
```

**Response:**
```json
{
  "session_id": "uuid",
  "bullets": ["bullet 1", "bullet 2", ...],
  "matches": [
    {
      "bullet_index": 0,
      "bullet_text": "...",
      "bullet_id": "uuid or null",
      "confidence": 0.95,
      "has_facts": true,
      "facts": {...} or null
    }
  ]
}
```

#### 2. Generate with Facts
```http
POST /v2/apply/generate_with_facts
Content-Type: application/json

{
  "user_id": "user-id",
  "job_description": "Full job description text...",
  "bullets": [
    {
      "bullet_text": "Original bullet text",
      "bullet_id": "uuid (optional - from match response)",
      "use_stored_facts": true
    }
  ]
}
```

**Response:**
```json
{
  "enhanced_bullets": [
    {
      "original": "...",
      "enhanced": "...",
      "used_facts": true
    }
  ],
  "scores": {
    "before_score": 67.5,
    "after_score": 84.0,
    "improvement": 16.5,
    "dimensions": {
      "before": {"relevance": 7, "specificity": 6, ...},
      "after": {"relevance": 9, "specificity": 8, ...}
    }
  }
}
```

---

### Flow 2: Keyword-Only Optimization (NEW - Fast)

**Use this when:** User wants quick ATS optimization without answering questions.

**Steps:**
```
1. POST /v2/apply/match_bullets
   → Upload resume (or use base resume)
   → Returns bullets (skip the matching logic if you want)

2. POST /v2/apply/generate_keywords_only  ← NEW ENDPOINT
   → Send bullets + job description
   → Fast keyword optimization only
   → Returns enhanced bullets with scores

3. POST /download
   → Send enhanced bullets + user_id + session_id
   → Returns optimized DOCX file
```

**New Endpoint Details:**

#### Generate Keywords Only
```http
POST /v2/apply/generate_keywords_only
Content-Type: application/json

{
  "user_id": "user-id",
  "job_description": "Full job description text...",
  "bullets": [
    {
      "bullet_text": "Original bullet text"
    }
  ]
}
```

**Response:**
```json
{
  "enhanced_bullets": [
    {
      "original": "Conducted market and portfolio analysis...",
      "enhanced": "Conducted market research and portfolio analysis...",
      "used_facts": false
    }
  ],
  "scores": {
    "before_score": 67.5,
    "after_score": 72.1,
    "improvement": 4.6,
    "dimensions": {...}
  },
  "optimization_mode": "keywords_only"
}
```

**Key Differences from Full Optimization:**
- ✅ NO fact matching needed
- ✅ NO bullet_id required
- ✅ NO use_stored_facts flag needed
- ✅ Faster response time (1 LLM call per bullet vs 3+)
- ✅ Still calculates comparative scores
- ⚠️ Less dramatic improvements (typically +2-5 points vs +10-20)
- ⚠️ Only terminology alignment, no new facts/metrics added

---

## Download Endpoint (Shared by Both Flows)

```http
POST /download
Content-Type: multipart/form-data

bullets: string (required - JSON array of enhanced bullets)
user_id: string (required)
session_id: string (optional - for session-based resume)
file: file (optional - uses base resume or session resume if not provided)
```

**bullets format (JSON string):**
```json
[
  {
    "original": "...",
    "enhanced": "...",
    "used_facts": true
  }
]
```

**Response:**
- DOCX file download with `Content-Disposition` header
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

---

## Keyword Optimization Algorithm

The keyword-only mode uses the **light_touch** approach (winner from testing):

### What It Does:
1. ✅ Swaps synonyms to match JD terminology (e.g., "built" → "developed")
2. ✅ Reorders words slightly if meaning unchanged
3. ✅ Uses JD phrasing for concepts already present

### What It Does NOT Do:
1. ❌ Add tools/technologies not mentioned
2. ❌ Add metrics or numbers not in original
3. ❌ Add audiences not mentioned (stakeholders, leadership, clients)
4. ❌ Add qualifiers that change scope (cross-functional, enterprise-wide, etc.)
5. ❌ Change what was actually done

### Test Results:
- **Keyword Improvement:** +1.81 points (1-10 scale)
- **Factual Preservation:** 7.58/10
- **Natural Flow:** 7.00/10
- **Total Score:** 7.10/100 (weighted)
- **% High Factual (≥8):** 55.6%

**Comparison to other approaches:**
- More factually accurate than "aggressive" (+4.14 keywords but 3.24/10 factual)
- Better keyword improvement than "synonym_only" (9.33/10 factual but -1.94 keywords)
- Sweet spot between accuracy and optimization

---

## Example Frontend Implementation

### Dual-Mode UI Example

```javascript
// User selects optimization mode
const optimizationMode = userSelectedMode; // "full" or "keywords"

// Step 1: Get bullets (shared)
const matchResponse = await fetch('/v2/apply/match_bullets', {
  method: 'POST',
  body: formData // contains user_id and optional resume_file
});

const { session_id, bullets, matches } = await matchResponse.json();

// Step 2: Generate (mode-dependent)
let generationEndpoint;
let requestBody;

if (optimizationMode === "full") {
  // Full optimization with facts
  generationEndpoint = '/v2/apply/generate_with_facts';
  requestBody = {
    user_id: userId,
    job_description: jobDescription,
    bullets: bullets.map((bullet, idx) => ({
      bullet_text: bullet,
      bullet_id: matches[idx].bullet_id, // Use matched bullet ID
      use_stored_facts: matches[idx].has_facts // Use facts if available
    }))
  };
} else {
  // Keyword-only optimization (FAST)
  generationEndpoint = '/v2/apply/generate_keywords_only';
  requestBody = {
    user_id: userId,
    job_description: jobDescription,
    bullets: bullets.map(bullet => ({
      bullet_text: bullet
      // No bullet_id or use_stored_facts needed!
    }))
  };
}

const generateResponse = await fetch(generationEndpoint, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(requestBody)
});

const { enhanced_bullets, scores } = await generateResponse.json();

// Step 3: Download (shared)
const downloadFormData = new FormData();
downloadFormData.append('bullets', JSON.stringify(enhanced_bullets));
downloadFormData.append('user_id', userId);
downloadFormData.append('session_id', session_id);
// Optional: append 'file' if you want to use a different resume

const downloadResponse = await fetch('/download', {
  method: 'POST',
  body: downloadFormData
});

const blob = await downloadResponse.blob();
const url = window.URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = 'resume_optimized.docx';
a.click();
```

---

## Migration from Old to New

### If you already have the full optimization flow:

1. Add a mode selector UI (toggle, radio buttons, or tabs)
2. Conditionally call different endpoints based on mode
3. Both flows use the same download endpoint
4. Both flows return the same enhanced_bullets format

### Minimal change example:

```diff
- const endpoint = '/v2/apply/generate_with_facts';
+ const endpoint = mode === 'full'
+   ? '/v2/apply/generate_with_facts'
+   : '/v2/apply/generate_keywords_only';

  const bullets = mode === 'full'
    ? matches.map(m => ({
        bullet_text: m.bullet_text,
        bullet_id: m.bullet_id,
        use_stored_facts: m.has_facts
      }))
    : bullets.map(b => ({ bullet_text: b })); // Simpler for keywords-only
```

---

## Error Handling

Both endpoints return HTTP 500 with error details:

```json
{
  "detail": "Error message"
}
```

Common errors:
- 400: Invalid request body
- 404: Session not found (for download)
- 500: LLM generation failed
- 503: Supabase not configured

---

## Performance Comparison

| Metric | Full Optimization | Keyword-Only |
|--------|------------------|--------------|
| API Calls | 3+ per bullet | 1 per bullet |
| User Input | Questions required | None |
| Time | 2-5 minutes | 10-30 seconds |
| Improvement | +10-20 points | +2-5 points |
| Factual Risk | Low (with facts) | Very Low |

---

## Recommended UX Flow

1. **Landing Page:** Show both options
   - "Full Optimization" (Best results, asks questions)
   - "Quick Keyword Boost" (Fast, no questions)

2. **Upload Resume:** Shared for both modes

3. **Fork:**
   - **Full Mode:** Show matched bullets, highlight which have facts, proceed to generation
   - **Keyword Mode:** Skip matching UI, go straight to generation

4. **Results:** Same for both - show before/after, scores, download button

5. **Messaging:**
   - Full: "Your resume improved by 18.5 points using your stored experience!"
   - Keyword: "Your resume is now ATS-optimized with better keyword alignment!"

---

## Testing

Test both endpoints:

```bash
# Test keyword-only (fast)
curl -X POST http://localhost:8000/v2/apply/generate_keywords_only \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "job_description": "Software Engineer with Python and React experience...",
    "bullets": [
      {"bullet_text": "Built web applications using modern frameworks"},
      {"bullet_text": "Analyzed data to improve product decisions"}
    ]
  }'

# Test full optimization (with facts)
curl -X POST http://localhost:8000/v2/apply/generate_with_facts \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "job_description": "Software Engineer with Python and React experience...",
    "bullets": [
      {
        "bullet_text": "Built web applications using modern frameworks",
        "use_stored_facts": false
      }
    ]
  }'
```
