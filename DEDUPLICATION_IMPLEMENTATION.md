# Deduplication Implementation (Rank 2 Approach)

## Problem Statement

When optimizing resume bullets individually, the LLM tends to reuse the same action verbs across multiple bullets. For example:

```
❌ BEFORE (repetitive):
- Generated insights from market analysis...
- Generated reports for executive team...
- Generated analytics framework...
```

This creates an unnatural, repetitive resume that reduces impact and readability.

---

## Solution: Post-Processing Deduplication Pass

**Approach:** After optimizing all bullets individually, run ONE additional LLM call to diversify vocabulary across the full set.

**Why Rank 2?**
- ✅ High effectiveness - directly targets the problem
- ✅ Minimal code changes - just add one extra step
- ✅ Preserves individual bullet optimization quality
- ✅ Easy to toggle on/off for testing
- ⚠️ +1 additional API call (adds ~2 seconds)

---

## Implementation

### 1. New Function: `deduplicate_repeated_words()`

**Location:** `llm_utils.py` lines 1318-1391

**Signature:**
```python
def deduplicate_repeated_words(optimized_bullets: List[str], job_description: str) -> List[str]
```

**What it does:**
1. Takes a list of already-optimized bullets
2. Formats them with numbers for clarity
3. Sends to LLM with instruction to diversify vocabulary
4. Parses response back into list
5. Returns deduplicated bullets in same order

**Key Features:**
- Maintains ALL facts and metrics (strict instruction)
- Maintains keyword alignment with job description
- Uses temperature=0.3 for slight creativity while staying conservative
- Robust parsing with fallback to original if parsing fails
- Skips deduplication for single bullet (no need)

**Prompt Strategy:**
```
RULES:
1. Keep ALL facts, metrics, tools, and accomplishments exactly as stated
2. Vary action verbs across bullets
3. Maintain keyword alignment with job description
4. Do NOT add new information, metrics, or claims
5. Do NOT remove any factual content

GOAL: Same factual content, same keyword optimization, but more varied vocabulary.
```

---

### 2. Endpoint Integration

**Location:** `app.py` lines 817-833

**Modified:** `/v2/apply/generate_keywords_only` endpoint

**Flow:**

#### Before (Single Pass):
```
For each bullet:
  optimize_keywords_light_touch(bullet) → enhanced_bullet
```

#### After (Two Pass):
```
Step 1: Individual Optimization
  For each bullet:
    optimize_keywords_light_touch(bullet) → optimized_bullet

Step 2: Deduplication
  deduplicate_repeated_words(all_optimized_bullets) → final_bullets

Step 3: Format Results
  Create {original, enhanced, used_facts} objects

Step 4: Calculate Scores
  Use final deduplicated bullets for scoring
```

**Code Changes:**
```python
# Step 1: Optimize each bullet individually
for idx, bullet_item in enumerate(request.bullets):
    enhanced_text = optimize_keywords_light_touch(
        bullet_text,
        request.job_description
    )
    enhanced_bullets.append(enhanced_text)

# Step 2: Deduplicate repeated words across all bullets
deduplicated_bullets = deduplicate_repeated_words(
    enhanced_bullets,
    request.job_description
)

# Step 3: Format results with deduplicated bullets
enhanced_bullets = []
for original, deduplicated in zip(original_bullets_list, deduplicated_bullets):
    enhanced_bullets.append({
        "original": original,
        "enhanced": deduplicated,  # Using deduplicated version
        "used_facts": False
    })
```

---

## Performance Impact

### API Calls:
- **Before:** N calls (one per bullet)
- **After:** N + 1 calls (N individual + 1 deduplication)
- **Example:** 8 bullets = 8 calls → 9 calls

### Time Impact:
- **Deduplication call:** ~2-3 seconds (single LLM call for all bullets)
- **Total increase:** ~2-3 seconds regardless of bullet count
- **Example:** 8 bullets: 24 seconds → 27 seconds (~12% increase)

### Token Cost:
- **Deduplication prompt:** ~200 tokens (job description + bullets + instructions)
- **Response:** ~400 tokens (all deduplicated bullets)
- **Total:** ~600 tokens per resume
- **Cost:** ~$0.01 per resume (with Claude Sonnet)

---

## Testing

### Manual Test Script

Run `test_deduplication.py` to see the deduplication in action:

```bash
python3 test_deduplication.py
```

**Expected Output:**
```
STEP 1: Individual Optimization
Optimizing bullet 1...
  Result: Generated pricing framework...
Optimizing bullet 2...
  Result: Generated market analysis...
Optimizing bullet 3...
  Result: Generated analytics solution...

⚠️  REPETITION DETECTED:
  - generated: 3 times

STEP 2: Deduplication Pass

DEDUPLICATED BULLETS:
1. Developed pricing framework...
2. Conducted market analysis...
3. Built analytics solution...

✅ IMPROVEMENT: Repetition reduced!
```

### Integration Test

Use the existing endpoint test:

```bash
python3 test_keyword_endpoint.py
```

Should now show **varied vocabulary** in the output bullets.

---

## Example Results

### Before Deduplication:
```
1. Generated pricing analytics framework to streamline regional planning
2. Generated market and portfolio analysis to identify expansion opportunities
3. Generated analytics framework to uncover retention drivers
```

**Problem:** "Generated" appears 3 times

### After Deduplication:
```
1. Developed pricing analytics framework to streamline regional planning
2. Conducted market and portfolio analysis to identify expansion opportunities
3. Built analytics framework to uncover retention drivers
```

**Result:** Varied verbs: "Developed", "Conducted", "Built" ✓

---

## Safeguards

### 1. Factual Preservation
- Explicit instruction: "Keep ALL facts, metrics, tools exactly as stated"
- Low temperature (0.3) for conservative changes
- No addition of new claims or information

### 2. Keyword Alignment
- Job description passed to deduplication prompt
- Instruction to maintain keyword alignment
- Only vocabulary diversity changes, not semantic content

### 3. Fallback Safety
```python
if len(deduplicated) != len(optimized_bullets):
    log.warning("Deduplication parsing failed. Using original.")
    return optimized_bullets
```

If parsing fails or count mismatches, returns the original optimized bullets (no deduplication but no data loss).

### 4. Single Bullet Skip
```python
if len(optimized_bullets) <= 1:
    return optimized_bullets
```

No API call wasted if there's only one bullet (no repetition possible).

---

## Monitoring

### Key Metrics to Track:

1. **Deduplication Success Rate**
   - % of requests where deduplication completes successfully
   - Track parsing failures

2. **Vocabulary Diversity**
   - Count unique action verbs before vs after
   - Measure reduction in repeated words

3. **Factual Preservation**
   - Spot-check: do deduplicated bullets maintain all facts?
   - User feedback on accuracy

4. **Performance Impact**
   - Average time for deduplication call
   - Total endpoint latency increase

5. **Quality Scores**
   - Do deduplicated bullets score higher or lower?
   - User satisfaction with final output

---

## Configuration Options

### Toggle Deduplication

To disable deduplication (for testing or rollback):

```python
# In app.py, comment out deduplication step:

# deduplicated_bullets = deduplicate_repeated_words(
#     enhanced_bullets,
#     request.job_description
# )
# deduplicated_bullets = enhanced_bullets  # Skip deduplication
```

### Adjust Temperature

More diversity (higher risk of drift):
```python
temperature=0.5  # More creative
```

Less diversity (more conservative):
```python
temperature=0.1  # Very conservative
```

---

## Future Improvements

### Rank 1 Upgrade: Batch Processing

If deduplication proves effective, upgrade to Rank 1 (batch processing):

**Benefits:**
- Even faster (1 API call instead of N+1)
- Better vocabulary awareness from the start
- Lower cost (fewer API calls)

**Implementation:**
- Replace per-bullet loop with single batch prompt
- Process all bullets in one LLM call
- Include diversity instruction in initial prompt

### Adaptive Deduplication

Only run deduplication if repetition is detected:

```python
# Quick check for repetition
action_verbs = extract_action_verbs(enhanced_bullets)
if has_repetition(action_verbs):
    deduplicated_bullets = deduplicate_repeated_words(...)
else:
    deduplicated_bullets = enhanced_bullets  # Skip unnecessary call
```

---

## Files Modified

1. **`llm_utils.py`**
   - Added `deduplicate_repeated_words()` function (lines 1318-1391)

2. **`app.py`**
   - Modified `/v2/apply/generate_keywords_only` endpoint (lines 795-833)
   - Added deduplication step between optimization and scoring

3. **New Files:**
   - `test_deduplication.py` - Manual test script
   - `DEDUPLICATION_IMPLEMENTATION.md` - This document

---

## Rollback Plan

If issues arise:

1. **Quick Disable:** Comment out deduplication call in `app.py`
2. **Full Rollback:** Revert to previous commit
3. **Fallback:** System already has fallback to original bullets if parsing fails

No risk of data loss or broken functionality.

---

## Success Criteria

✅ **Implemented if:**
- Deduplication function added to `llm_utils.py`
- Endpoint integrated with deduplication step
- Test script passes

✅ **Working if:**
- Repetitive words reduced in output
- All facts preserved
- No parsing errors
- Acceptable performance impact (<5 seconds added)

✅ **Success if:**
- Users report more natural-sounding resumes
- Vocabulary diversity increases measurably
- No complaints about factual accuracy
- Quality scores remain stable or improve

---

## Summary

**What was added:**
- One new function (~70 lines)
- One integration step (~20 lines)
- One test script (~100 lines)

**What it does:**
- Removes repetitive vocabulary across bullets
- Preserves all facts and keyword alignment
- Adds ~2 seconds to total optimization time

**Why it's valuable:**
- Resumes sound more natural and professional
- Reduces robotic/template feel
- Improves readability and impact
- Minimal cost for significant quality improvement

**Next steps:**
1. Test with `test_deduplication.py`
2. Monitor performance and quality metrics
3. Consider upgrade to Rank 1 (batch processing) if successful
