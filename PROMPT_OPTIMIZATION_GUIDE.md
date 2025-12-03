# Prompt Optimization Framework

Systematic approach to improving resume bullet optimization prompts using LLM-as-judge and iterative refinement.

## Overview

This framework tests your prompts against **9 diverse bullets** (4 with context, 5 without) across **7 different job types** for a total of **63 test cases**. It evaluates:

- ✅ WITH-FACTS path (uses stored context)
- ✅ NO-FACTS path (anti-hallucination mode)
- ✅ Cross-industry generalization (tech, business, operations, sales, marketing, etc.)

## Files

- **`test_fixtures.yaml`** - Test bullets + 7 job descriptions with diverse roles
- **`evaluate_prompts.py`** - Runs current prompts and uses LLM-as-judge to score results
- **`optimize_prompts.py`** - Uses LLM to suggest prompt improvements based on eval results

---

## Quick Start

### 1. Run Baseline Evaluation

```bash
python evaluate_prompts.py --save baseline_results.json
```

**Output:**
- Runs all 63 test cases (9 bullets × 7 job types)
- Scores each on 6 dimensions (1-10):
  - Relevance to JD
  - Conciseness
  - Impact & Metrics
  - Action Verbs
  - Factual Accuracy (critical for NO-FACTS)
  - Keyword Alignment
- Prints summary with averages by context type and job type
- Saves detailed results to JSON

**Expected time:** ~10-15 minutes (depends on API speed)

### 2. Get LLM Suggestions for Improvement

```bash
python optimize_prompts.py baseline_results.json
```

**Output:**
- Analyzes weak dimensions and common issues
- Uses LLM to suggest specific prompt improvements
- Saves suggestions to `prompt_suggestions_with_facts.txt` and `prompt_suggestions_no_facts.txt`

### 3. Update Prompts in `llm_utils.py`

Review the suggestions and manually update:
- **WITH-FACTS prompt**: Line ~729 in `generate_bullet_with_facts()`
- **NO-FACTS prompt**: Line ~364 in `_generate_bullet_without_facts()`

### 4. Re-evaluate

```bash
python evaluate_prompts.py --save improved_results.json
```

### 5. Compare Results

```bash
# Quick comparison
python -c "
import json
baseline = json.load(open('baseline_results.json'))
improved = json.load(open('improved_results.json'))
baseline_avg = sum(r['scores']['total'] for r in baseline['results']) / len(baseline['results'])
improved_avg = sum(r['scores']['total'] for r in improved['results']) / len(improved['results'])
print(f'Baseline: {baseline_avg:.2f}/10')
print(f'Improved: {improved_avg:.2f}/10')
print(f'Change: {improved_avg - baseline_avg:+.2f}')
"
```

### 6. Iterate

If results improved → commit changes!
If not → analyze issues, try different approach, repeat.

---

## Advanced Usage

### Verbose Mode (See All Outputs)

```bash
python evaluate_prompts.py --verbose --save results.json
```

Shows original vs optimized bullets for every test case.

### Test Single Prompt Type

```bash
# Only optimize NO-FACTS prompt
python optimize_prompts.py baseline_results.json --prompt-type no_facts

# Only optimize WITH-FACTS prompt
python optimize_prompts.py baseline_results.json --prompt-type with_facts
```

### Add More Test Cases

Edit `test_fixtures.yaml`:

```yaml
bullets:
  - id: "new_bullet_with_context"
    bullet: "Your bullet text here"
    has_context: true
    facts:
      tools: ["Python", "SQL"]
      actions: ["Built X", "Analyzed Y"]
      results: ["Achieved Z"]
      # ... etc

  - id: "new_bullet_no_context"
    bullet: "Another bullet"
    has_context: false
    facts: {}
```

### Add More Job Types

Edit `test_fixtures.yaml`:

```yaml
job_descriptions:
  - id: "new_job_type"
    title: "New Role Title"
    type: "category"
    description: |
      Full job description here...
      Include key skills, responsibilities, requirements.
```

---

## Understanding the Scores

### Dimension Scores (1-10 each)

| Dimension | What It Measures | Good Score |
|-----------|------------------|------------|
| **Relevance** | Alignment with JD skills/tech | 7.5+ |
| **Conciseness** | Tight writing, no filler | 7.0+ |
| **Impact** | Clear metrics and achievements | 7.5+ |
| **Action Verbs** | Strong ownership language | 7.5+ |
| **Factual Accuracy** | No hallucination (critical!) | 9.0+ |
| **Keyword Alignment** | Uses JD terminology | 7.0+ |

### Total Score Interpretation

- **9.0-10.0**: Excellent - minimal improvements needed
- **7.5-8.9**: Good - minor tweaks for polish
- **6.0-7.4**: Needs work - several dimensions weak
- **4.0-5.9**: Poor - major prompt issues
- **<4.0**: Critical - prompt fundamentally broken

### What to Look For

**High-performing bullets:**
- Score consistently 7.5+ across job types
- Maintain factual accuracy (9-10) when no context
- Show strong action verbs (8+) with context

**Problem areas:**
- Conciseness < 6.5 → Too verbose, add "END ON STRONGEST POINT" guidance
- Factual accuracy < 8 without context → Strengthen anti-hallucination rules
- Action verbs < 7 → Add examples of strong vs weak verbs
- Relevance varies widely by job type → Improve cross-industry generalization

---

## Common Issues & Fixes

### Issue: Verbose bullets with trailing clauses

**Symptoms:** Conciseness scores 5-6
**Fix:** Add explicit "END ON STRONGEST POINT" examples

```
❌ "Reduced costs by 40% through rigorous process optimization..."
✅ "Reduced costs by 40% through vendor renegotiation"
```

### Issue: Hallucination in NO-FACTS path

**Symptoms:** Factual accuracy < 8 without context
**Fix:** Strengthen anti-hallucination language:
- Add "ZERO ADDITIONS" rule with examples
- Add validation checklist
- Emphasize "ONLY use what's explicitly stated"

### Issue: Weak action verbs

**Symptoms:** Action verbs scores < 7
**Fix:**
- Add explicit "DO NOT weaken verbs" guidance
- Provide bad → good examples
- List strong verbs at top of prompt

### Issue: Poor cross-industry performance

**Symptoms:** Scores vary wildly by job type (e.g., 8.5 for tech, 5.0 for business)
**Fix:**
- Make instructions more general, less tech-specific
- Add examples from multiple domains
- Test thoroughly across all job types before committing

---

## Workflow for Major Prompt Refactors

1. **Create branch**
   ```bash
   git checkout -b prompt-optimization-v2
   ```

2. **Run baseline**
   ```bash
   python evaluate_prompts.py --save baseline.json
   ```

3. **Make changes to prompts in `llm_utils.py`**

4. **Evaluate incrementally**
   ```bash
   python evaluate_prompts.py --save iteration1.json
   # Review, adjust
   python evaluate_prompts.py --save iteration2.json
   # Keep iterating
   ```

5. **When satisfied, commit**
   ```bash
   git add llm_utils.py
   git commit -m "Improve prompt: +1.2 avg score, fixed conciseness issues"
   ```

6. **Compare final vs baseline**
   ```bash
   # Should show clear improvement across dimensions
   ```

---

## Tips for Effective Optimization

### Do's ✅

- Test across all job types before committing
- Focus on worst-performing dimensions first
- Use concrete examples in prompts (before/after)
- Make one change at a time, measure impact
- Keep anti-hallucination rules strict for NO-FACTS
- Preserve what's working well

### Don'ts ❌

- Don't overfit to specific test cases
- Don't make prompts too rigid/prescriptive
- Don't weaken anti-hallucination for variety
- Don't commit without measuring impact
- Don't ignore cross-industry performance

---

## Troubleshooting

### "Module not found" errors

```bash
# Make sure you're in the resume_customizer directory
cd /home/user/resume_customizer

# Check that config.py and llm_utils.py exist
ls -la config.py llm_utils.py
```

### Evaluation taking too long

```bash
# Test with smaller subset first
# Edit test_fixtures.yaml and comment out some job descriptions
# Or test single bullet:
python -c "
from evaluate_prompts import *
# Run custom evaluation logic here
"
```

### LLM judge giving inconsistent scores

- LLM judges can vary. Run evaluation 2-3 times and average.
- Use temperature=0 for judge (already set in evaluate_prompts.py)
- If still inconsistent, make evaluation criteria more precise

---

## Success Metrics

Target scores after optimization:

- **Overall average**: 7.5+ / 10
- **With context**: 8.0+ / 10
- **Without context**: 7.0+ / 10
- **Factual accuracy (no context)**: 9.0+ / 10
- **All job types**: Within 1.0 point of each other (good generalization)

---

## Questions?

This framework should help you systematically improve prompts with objective measurements. The key is:

1. **Measure** (baseline eval)
2. **Identify** (analyze weak dimensions)
3. **Improve** (update prompts)
4. **Measure** (eval again)
5. **Repeat** until satisfied

Happy optimizing! 🚀
