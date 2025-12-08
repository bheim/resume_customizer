import re, hashlib, json
from json import loads
from typing import List, Dict, Optional, Tuple
from config import client, openai_client, CHAT_MODEL, EMBED_MODEL, USE_DISTILLED_JD, USE_LLM_TERMS, log
from text_utils import top_terms

_distill_cache: Dict[str, str] = {}
_terms_cache: Dict[str, Dict[str, List[str]]] = {}

def jd_hash(jd_text: str) -> str:
    return hashlib.sha256(jd_text.encode("utf-8")).hexdigest()

def llm_distill_jd(jd_text: str) -> str:
    if not client or not jd_text.strip(): return jd_text
    h = jd_hash(jd_text)
    if h in _distill_cache: return _distill_cache[h]
    prompt = f"""Distill the JOB DESCRIPTION into a focused role core (8–12 bullet-like lines), excluding perks, benefits, compensation, culture, location, legal/EEO, boilerplate.
Include only: core responsibilities, required skills/tools, domain focus, seniority/scope.
Return plain text only.

JOB DESCRIPTION:
{jd_text}
"""
    r = client.messages.create(model=CHAT_MODEL, max_tokens=1024, messages=[{"role":"user","content":prompt}], temperature=0)
    distilled = (r.content[0].text or "").strip()
    if not distilled or len(distilled) < 40: distilled = jd_text
    _distill_cache[h] = distilled
    log.info(f"The distilled job description is {distilled}")
    return distilled

def llm_extract_terms(jd_text: str) -> Dict[str, List[str]]:
    if not client or not jd_text.strip():
        return {"skills": [], "tools": [], "domains": [], "responsibilities": [], "seniority": [], "certifications": []}
    h = "terms:" + jd_hash(jd_text)
    if h in _terms_cache: return _terms_cache[h]
    prompt = f"""Extract role-critical keywords from the JOB DESCRIPTION as strict JSON.
Exclude benefits, perks, location, compensation, culture, legal, EEO, boilerplate.
Groups:
- skills
- tools
- domains
- responsibilities
- seniority
- certifications
Do NOT include generic soft skills like "effective communication", "team player", "self-starter".
Output JSON ONLY with those keys and arrays.

JOB DESCRIPTION:
{jd_text}
"""
    r = client.messages.create(model=CHAT_MODEL, max_tokens=1024, messages=[{"role":"user","content":prompt}], temperature=0)
    raw = (r.content[0].text or "").strip()
    try:
        data = loads(raw)
    except Exception:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = re.sub(r"^\s*json", "", cleaned, flags=re.I).strip()
        data = loads(cleaned)
    out = {k: sorted(set([t.strip() for t in data.get(k, []) if isinstance(t, str) and t.strip()])) for k in
           ["skills","tools","domains","responsibilities","seniority","certifications"]}
    _terms_cache[h] = out
    log.info(f"The key terms for this job are {out}")


    return out

def embed(text: str) -> List[float]:
    if not openai_client: return []
    resp = openai_client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding

def llm_fit_score(resume_text: str, jd_text: str) -> float:
    if not client: return 0.0
    prompt = f"""You are a strict recruiter. Score how well the RESUME matches the JOB DESCRIPTION on a 0–100 scale.
Consider skill/domain alignment, scope, seniority, quantified impact, tools/tech, responsibilities.
Return ONLY a number 0–100.

JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_text}
"""
    r = client.messages.create(model=CHAT_MODEL, max_tokens=64, messages=[{"role":"user","content":prompt}], temperature=0)
    out = (r.content[0].text or "").strip()
    m = re.search(r"(\d{1,3})", out)
    if not m: return 0.0
    val = max(0, min(100, int(m.group(1))))
    return float(val)


def llm_comparative_score(original_bullets: List[str], enhanced_bullets: List[str], jd_text: str) -> Dict:
    """
    Comparative LLM grading of original vs enhanced resume bullets.

    Evaluates both sets of bullets independently as a hiring manager on 5 dimensions:
    - Relevance to JD (30% weight)
    - Specificity & Impact (25% weight)
    - Language Strength (20% weight)
    - ATS Alignment (15% weight)
    - Overall Impression (10% weight)

    Args:
        original_bullets: List of original resume bullets
        enhanced_bullets: List of enhanced resume bullets
        jd_text: Job description text

    Returns:
        Dict with before_score, after_score, improvement, and dimension breakdowns:
        {
            "before_score": 67.5,
            "after_score": 84.0,
            "improvement": 16.5,
            "dimensions": {
                "before": {"relevance": 7, "specificity": 6, "language": 7, "ats": 6, "overall": 7},
                "after": {"relevance": 9, "specificity": 8, "language": 9, "ats": 8, "overall": 8}
            }
        }
    """
    if not client:
        return {
            "before_score": 0.0,
            "after_score": 0.0,
            "improvement": 0.0,
            "dimensions": {
                "before": {"relevance": 0, "specificity": 0, "language": 0, "ats": 0, "overall": 0},
                "after": {"relevance": 0, "specificity": 0, "language": 0, "ats": 0, "overall": 0}
            }
        }

    # Format bullets for evaluation
    original_text = "\n".join([f"• {b}" for b in original_bullets])
    enhanced_text = "\n".join([f"• {b}" for b in enhanced_bullets])

    # Randomize which set is presented as "Set A" vs "Set B" to avoid bias
    import random
    is_original_first = random.choice([True, False])
    set_a = original_text if is_original_first else enhanced_text
    set_b = enhanced_text if is_original_first else original_text

    prompt = f"""You are a hiring manager evaluating resume bullets for this position. You will review two anonymized sets of resume bullets and score each independently.

JOB DESCRIPTION:
{jd_text}

---

SET A:
{set_a}

SET B:
{set_b}

---

EVALUATION TASK:
Evaluate each set independently on these 5 dimensions (score 1-10 for each):

1. **Relevance to Job Requirements** (1-10)
   - How well do the bullets align with the specific skills, technologies, and responsibilities in the JD?
   - Do they address the core competencies needed for this role?

2. **Specificity & Impact** (1-10)
   - Are accomplishments quantified with metrics, percentages, or concrete outcomes?
   - Is the scope and scale clear (team size, budget, timeline)?
   - Do they demonstrate measurable business impact?

3. **Language Strength** (1-10)
   - Strong action verbs and professional tone?
   - Clear, concise, and compelling writing?
   - Demonstrates ownership and initiative?

4. **ATS Optimization** (1-10)
   - Uses relevant keywords from the job description?
   - Includes specific technologies, tools, and methodologies mentioned in JD?
   - Formatted for applicant tracking system parsing?

5. **Overall Impression** (1-10)
   - Would this candidate get an interview based on these bullets?
   - Do the bullets tell a compelling career story?
   - Overall professionalism and quality?

---

SCORING WEIGHTS (for reference):
- Relevance: 30%
- Specificity & Impact: 25%
- Language Strength: 20%
- ATS Alignment: 15%
- Overall Impression: 10%

---

OUTPUT FORMAT:
Return ONLY valid JSON in this exact format (no commentary, no code fences):

{{
  "set_a": {{
    "relevance": 8,
    "specificity": 7,
    "language": 8,
    "ats": 7,
    "overall": 8
  }},
  "set_b": {{
    "relevance": 9,
    "specificity": 9,
    "language": 9,
    "ats": 8,
    "overall": 9
  }}
}}

Evaluate objectively and independently. Each dimension should be scored 1-10."""

    try:
        r = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=0  # Deterministic for consistent grading
        )

        raw = (r.content[0].text or "").strip()

        # Clean potential code fences
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = re.sub(r"^\s*json", "", raw, flags=re.I).strip()

        scores = loads(raw)

        # Extract dimension scores
        set_a_scores = scores.get("set_a", {})
        set_b_scores = scores.get("set_b", {})

        # Calculate weighted totals (0-100 scale)
        def calculate_weighted_score(dims: Dict) -> float:
            relevance = dims.get("relevance", 0)
            specificity = dims.get("specificity", 0)
            language = dims.get("language", 0)
            ats = dims.get("ats", 0)
            overall = dims.get("overall", 0)

            # Weighted sum: each dimension is 1-10, convert to 0-100 scale
            weighted = (
                relevance * 0.30 +
                specificity * 0.25 +
                language * 0.20 +
                ats * 0.15 +
                overall * 0.10
            )
            return weighted * 10  # Convert to 0-100 scale

        set_a_total = calculate_weighted_score(set_a_scores)
        set_b_total = calculate_weighted_score(set_b_scores)

        # Map back to original/enhanced based on randomization
        if is_original_first:
            before_score = set_a_total
            after_score = set_b_total
            before_dims = set_a_scores
            after_dims = set_b_scores
        else:
            before_score = set_b_total
            after_score = set_a_total
            before_dims = set_b_scores
            after_dims = set_a_scores

        improvement = after_score - before_score

        result = {
            "before_score": round(before_score, 1),
            "after_score": round(after_score, 1),
            "improvement": round(improvement, 1),
            "dimensions": {
                "before": before_dims,
                "after": after_dims
            }
        }

        log.info(f"Comparative scoring: before={result['before_score']}, after={result['after_score']}, improvement={result['improvement']}")
        return result

    except Exception as e:
        log.exception(f"Error in comparative scoring: {e}")
        # Return neutral scores on error
        return {
            "before_score": 0.0,
            "after_score": 0.0,
            "improvement": 0.0,
            "dimensions": {
                "before": {"relevance": 0, "specificity": 0, "language": 0, "ats": 0, "overall": 0},
                "after": {"relevance": 0, "specificity": 0, "language": 0, "ats": 0, "overall": 0}
            }
        }

def should_ask_more_questions(answered_qa: List[Dict[str, str]], bullets: List[str],
                              job_description: str) -> Tuple[bool, str]:
    """
    Determine if more follow-up questions are needed based on existing answers.

    Args:
        answered_qa: List of answered Q&A pairs
        bullets: Original resume bullets
        job_description: Target job description

    Returns:
        Tuple of (should_ask_more, reason)
    """
    if not client:
        return False, "Anthropic client not available"

    if len(answered_qa) == 0:
        return True, "No questions answered yet"

    # Ask LLM if we have enough context
    qa_text = "\n".join([f"Q: {qa['question']}\nA: {qa['answer']}" for qa in answered_qa])
    bullets_text = "\n".join([f"{i+1}. {b}" for i, b in enumerate(bullets)])

    prompt = f"""You are evaluating if there is enough context to write strong, tailored resume bullets.

IMPORTANT: Be conservative. Only ask for more information if there are CLEAR, CRITICAL gaps. If you have enough information to write solid bullets with metrics and impact, say YES.

ORIGINAL BULLETS:
{bullets_text}

TARGET JOB:
{job_description}

INFORMATION GATHERED ({len(answered_qa)} questions answered):
{qa_text}

Based on this information, do you have enough context to write compelling, tailored resume bullets with metrics, impact, and relevant technical details?

Be biased towards YES - only say NO if there are critical missing pieces of information.

Answer with ONLY "YES" or "NO" followed by a brief reason (one sentence).
Format: YES|reason or NO|reason"""

    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    response = (r.content[0].text or "").strip()

    # Parse response
    if response.startswith("YES"):
        reason = response.split("|", 1)[1] if "|" in response else "Sufficient context"
        return False, reason
    else:
        reason = response.split("|", 1)[1] if "|" in response else "Need more context"
        return True, reason


def _generate_bullet_without_facts(original_bullet: str, job_description: str,
                                   char_limit: Optional[int] = None) -> str:
    """
    Conservative bullet optimization WITHOUT stored facts.

    ANTI-HALLUCINATION STRATEGY:
    - Preserves ALL original information exactly
    - Only modifies: action verbs, structure, keyword alignment
    - Forbidden: Adding metrics, technologies, or any new details
    - Multiple validation layers in prompt to prevent invention

    This ensures bullets without context still get optimized for the JD
    while maintaining 100% factual accuracy to the original.
    """
    log.debug(f"_generate_bullet_without_facts called")
    log.debug(f"  Original: '{original_bullet}'")
    log.debug(f"  JD length: {len(job_description)} chars")
    log.debug(f"  Char limit: {char_limit}")

    char_limit_text = (
        f"\n\nCHARACTER LIMIT: Keep the bullet under {char_limit} characters."
        if char_limit else ""
    )

    prompt = f"""You are a professional resume writer. Optimize this bullet for the target job description while preserving ALL factual content.

⚠️  CRITICAL ANTI-HALLUCINATION RULES - STRICTLY ENFORCED:

1. PRESERVE EVERYTHING: Keep every metric, number, percentage, timeframe, technology, tool, and detail EXACTLY as stated in the original
2. ZERO ADDITIONS: Do NOT add any metrics, technologies, team sizes, timeframes, or accomplishments not explicitly in the original
3. ZERO INVENTIONS: Do NOT make up numbers, percentages, outcomes, or specifics of any kind
4. FACT-CHECK YOURSELF: Every claim in your output must have a direct source in the original bullet

✅ WHAT YOU CAN DO (Surface-level optimization only):
• Strengthen action verbs to match job description tone
  Examples: "worked on" → "developed", "helped with" → "contributed to", "did" → "executed"

• Restructure using impact-first formats (use variety, NOT the same structure for every bullet):
  - "[Action] [X] resulting in [Y]"
  - "[Action] [X] by doing [Z]"
  - "[Action] [X], achieving [Y]"
  - "[Action] [X] to drive [Y]"
  - "[Action] [X] through [Z]"

• Align terminology with job description keywords (keep meaning identical)
  If JD says "engineered" instead of "built", swap them. If JD says "optimized" instead of "improved", swap them.

• Improve readability and flow - make it punchy and clear
• Reorder information to lead with impact

❌ WHAT YOU ABSOLUTELY CANNOT DO:
• Add metrics not in original (team size, percentages, numbers, timeframes)
• Add technologies or tools not mentioned
• Add scope details or project specifics
• Invent accomplishments or outcomes
• Embellish or exaggerate existing facts
• Add implied information - only use what's explicitly stated

ORIGINAL BULLET (this is your ONLY source of truth):
{original_bullet}

TARGET JOB DESCRIPTION (for keyword alignment only):
{job_description}{char_limit_text}

VALIDATION CHECKLIST (mentally verify before responding):
□ Every number in output appears in original?
□ Every technology in output appears in original?
□ Every metric in output appears in original?
□ Every claim can be traced to original?

Return ONLY the optimized bullet text. No explanations, no commentary."""

    try:
        log.debug(f"  Calling Anthropic with temperature=0.3")
        response = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3  # Slightly higher for variety, still controlled
        )
        enhanced = response.content[0].text.strip()

        log.info(f"  LLM returned: '{enhanced[:100]}...'")
        log.debug(f"  Full LLM response: '{enhanced}'")

        # Post-processing validation: log if output seems suspiciously longer
        if len(enhanced) > len(original_bullet) * 1.5:
            log.warning(
                f"No-facts optimization increased length significantly. "
                f"Original: {len(original_bullet)} chars, Enhanced: {len(enhanced)} chars. "
                f"Potential hallucination risk."
            )

        # Check if unchanged
        if enhanced == original_bullet:
            log.info(f"  LLM returned bullet unchanged (may be intentional if already good)")
        else:
            log.info(f"  Bullet modified - Original len: {len(original_bullet)}, Enhanced len: {len(enhanced)}")

        return enhanced

    except Exception as e:
        log.exception(f"Error in no-facts bullet generation: {e}")
        log.error(f"  Falling back to original bullet")
        # Fallback: return original if generation fails
        return original_bullet


def generate_bullet_with_facts(original_bullet: str, job_description: str,
                               stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Generate enhanced bullet using stored facts instead of raw Q&A.

    This is the optimized generation flow that uses pre-extracted, user-confirmed facts.

    Two optimization paths:
    1. WITH FACTS: Uses stored facts to enhance with specific details
    2. WITHOUT FACTS: Conservative optimization preserving ALL original information

    Args:
        original_bullet: The original bullet text
        job_description: Target job description
        stored_facts: Structured facts from extract_facts_from_qa() (can be empty {})
        char_limit: Optional character limit for the bullet

    Returns:
        Enhanced bullet string
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    # Detect if we have meaningful facts
    has_meaningful_facts = bool(
        stored_facts and
        any(stored_facts.get(category) for category in
            ["tools", "skills", "actions", "results", "situation", "timeline"])
    )

    # Detailed logging for path detection
    log.info(f"generate_bullet_with_facts - Bullet: '{original_bullet[:60]}...'")
    log.info(f"  stored_facts keys: {list(stored_facts.keys()) if stored_facts else 'None'}")
    log.info(f"  has_meaningful_facts: {has_meaningful_facts}")

    # PATH 1: No facts - use conservative no-hallucination prompt
    if not has_meaningful_facts:
        log.info(f"  → Taking NO-FACTS path (conservative optimization)")
        result = _generate_bullet_without_facts(
            original_bullet,
            job_description,
            char_limit
        )
        log.info(f"  → No-facts result: '{result[:80]}...'")
        if result == original_bullet:
            log.warning(f"  ⚠️  No-facts optimization returned UNCHANGED bullet")
        return result

    # PATH 2: With facts - use existing fact-based generation
    # Build facts context from stored facts
    facts_text = ""

    # Format facts using the current schema (situation, actions, results, skills, tools, timeline)
    if stored_facts.get("situation"):
        facts_text += f"Situation/Context: {stored_facts['situation']}\n"

    if stored_facts.get("actions"):
        actions = stored_facts["actions"]
        if isinstance(actions, list) and actions:
            facts_text += "Actions Taken:\n"
            for item in actions:
                facts_text += f"• {item}\n"

    if stored_facts.get("results"):
        results = stored_facts["results"]
        if isinstance(results, list) and results:
            facts_text += "Results/Achievements:\n"
            for item in results:
                facts_text += f"• {item}\n"

    if stored_facts.get("skills"):
        skills = stored_facts["skills"]
        if isinstance(skills, list) and skills:
            facts_text += f"Skills: {', '.join(skills)}\n"

    if stored_facts.get("tools"):
        tools = stored_facts["tools"]
        if isinstance(tools, list) and tools:
            facts_text += f"Tools/Technologies: {', '.join(tools)}\n"

    if stored_facts.get("timeline"):
        facts_text += f"Timeline: {stored_facts['timeline']}\n"

    char_limit_text = f"\nIMPORTANT: Keep the bullet under {char_limit} characters." if char_limit else ""

    log.info(f"  → Taking WITH-FACTS path (rich optimization)")
    log.debug(f"  Facts text length: {len(facts_text)} chars")

    prompt = f"""You are a professional resume writer creating a new, optimized bullet point.

            Your task: Construct a compelling bullet from scratch using the verified facts below, optimized for the target job description. The original bullet is provided only as context for what experience this covers—do not simply edit it.

            TARGET JOB DESCRIPTION:
            {job_description}

            VERIFIED FACTS TO USE:
            {facts_text}

REWRITING GUIDELINES:

1. ACTION VERBS - Preserve or strengthen ownership language:
   • If the original verb shows creation/leadership (Developed, Led, Built, Architected, Designed), keep it or use an equally strong verb
   • Don't weaken "Developed" → "Streamlined" or "Led" → "Supported"
   • Strong verbs: Led, Developed, Engineered, Optimized, Architected, Drove, Delivered, Built, Designed, Implemented, Spearheaded, Created
   • Choose verbs that match the job description's language while maintaining ownership

2. FACT SELECTION - Quality over quantity:
   • Select the 1-2 most impressive, relevant facts
   • Don't try to incorporate every detail - one powerful metric beats three mediocre ones
   • If a fact doesn't fit naturally in a concise bullet, drop it

3. METRIC CLARITY - State each metric once in its most compelling form:
   • Don't restate the same achievement multiple ways
   • Choose the most impactful representation

4. CONCISENESS - Every word must earn its place:
   • Cut ruthlessly - aim for maximum impact in minimum words
   • Remove descriptive filler: "comprehensive", "utilizing", "leveraging", "extensive"
   • Don't explain the obvious: if you analyzed data, skip "through data-driven insights"
   • Each detail must pass the "so what?" test - does it make the achievement more impressive, or just longer?
   • Technical details (tools/methods) should only be included if:
     - Specifically mentioned in the job description, OR
     - Highly specialized/impressive for the role
     - Generic phrases like "statistical methods" add no value - cut them

   END ON THE STRONGEST POINT:
   • Bullets should end with the most impactful element - usually the quantified result
   • After stating the concrete outcome, STOP
   • Don't add trailing "through X" or "via Y" or "derived from Z" clauses
   • These explanatory tails weaken the ending and add no concrete value

   Example:
   ❌ "Reduced costs by 40% through rigorous process optimization and strategic vendor negotiations"
   ✅ "Reduced costs by 40% through vendor renegotiation"

   The result (40% reduction) is the punch line - end there or immediately after the key method.

5. STRUCTURE VARIETY - Use different formats across bullets:
   • "[Action] [X] resulting in [Y]"
   • "[Action] [X], achieving [Y]"
   • "[Action] [X] by doing [Z]"
   • "[Action] [X] to [concrete outcome]"
   • "[Action] [X] through [Z], delivering [Y]"
   • Vary structure - don't make all bullets sound the same

6. ALIGNMENT - Match job description requirements and terminology

7. DO NOT add information not present in the facts above{char_limit_text}

            Return ONLY the new bullet."""

    # Log the full prompt so it's visible in logs
    log.info(f"  ===== WITH-FACTS PROMPT START =====")
    log.info(prompt)
    log.info(f"  ===== WITH-FACTS PROMPT END =====")

    log.debug(f"  Calling Anthropic with temperature=0.4 for variety")
    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4  # Higher for structural variety while staying factual
    )

    enhanced_bullet = (r.content[0].text or "").strip()

    # Clean up any bullet markers or extra formatting
    enhanced_bullet = enhanced_bullet.lstrip("-• ").strip()

    log.info(f"  → With-facts result: '{enhanced_bullet[:80]}...'")
    log.info(f"  → Generated bullet: {len(enhanced_bullet)} chars")
    log.debug(f"  Full bullet: '{enhanced_bullet}'")

    return enhanced_bullet


def generate_bullet_with_facts_scaffolded(original_bullet: str, job_description: str,
                                         stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Two-stage scaffolded bullet generation:
    1. Select most relevant facts for the JD
    2. Craft bullet using only selected facts

    This approach forces explicit prioritization before writing.

    Args:
        original_bullet: The original bullet text
        job_description: Target job description
        stored_facts: Structured facts from extract_facts_from_qa() (can be empty {})
        char_limit: Optional character limit for the bullet

    Returns:
        Enhanced bullet string
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    # Detect if we have meaningful facts
    has_meaningful_facts = bool(
        stored_facts and
        any(stored_facts.get(category) for category in
            ["tools", "skills", "actions", "results", "situation", "timeline"])
    )

    log.info(f"generate_bullet_with_facts_SCAFFOLDED - Bullet: '{original_bullet[:60]}...'")
    log.info(f"  has_meaningful_facts: {has_meaningful_facts}")

    # If no facts, use the same conservative path as single-stage
    if not has_meaningful_facts:
        log.info(f"  → Taking NO-FACTS path (same as single-stage)")
        return _generate_bullet_without_facts(
            original_bullet,
            job_description,
            char_limit
        )

    # STAGE 1: Select most relevant facts
    log.info(f"  → STAGE 1: Selecting most relevant facts")

    # Format available facts
    facts_list = []
    if stored_facts.get("situation"):
        facts_list.append(f"Context: {stored_facts['situation']}")

    if stored_facts.get("actions"):
        for action in stored_facts["actions"]:
            facts_list.append(f"Action: {action}")

    if stored_facts.get("results"):
        for result in stored_facts["results"]:
            facts_list.append(f"Result: {result}")

    if stored_facts.get("skills"):
        facts_list.append(f"Skills: {', '.join(stored_facts['skills'])}")

    if stored_facts.get("tools"):
        facts_list.append(f"Tools: {', '.join(stored_facts['tools'])}")

    if stored_facts.get("timeline"):
        facts_list.append(f"Timeline: {stored_facts['timeline']}")

    facts_enumerated = "\n".join([f"{i+1}. {fact}" for i, fact in enumerate(facts_list)])

    selection_prompt = f"""You are helping optimize a resume bullet for a specific job.

TARGET JOB DESCRIPTION:
{job_description}

ORIGINAL BULLET:
{original_bullet}

AVAILABLE FACTS:
{facts_enumerated}

Your task: Select the 2-3 most impactful facts that:
1. Are most relevant to the target job description
2. Demonstrate the strongest achievements/skills
3. Will create the most compelling bullet when combined

Consider:
- What does this job emphasize? (technical skills, leadership, impact, specific tools?)
- Which facts would make a hiring manager think "this person is perfect for this role"?
- Quality over quantity - fewer powerful facts beat many weak ones

Return ONLY valid JSON (no commentary):
{{
  "selected_facts": ["fact #X", "fact #Y", ...],
  "reasoning": "Brief explanation of why these facts matter most for THIS job"
}}"""

    log.debug(f"  Selection prompt created, calling Anthropic")

    r1 = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": selection_prompt}],
        temperature=0  # Deterministic selection
    )

    selection_raw = (r1.content[0].text or "").strip()

    # Clean code fences if present
    if selection_raw.startswith("```"):
        selection_raw = selection_raw.strip("`")
        selection_raw = re.sub(r"^\s*json", "", selection_raw, flags=re.I).strip()

    try:
        selection_data = json.loads(selection_raw)
        selected_facts = selection_data.get("selected_facts", [])
        reasoning = selection_data.get("reasoning", "")

        log.info(f"  → Selected {len(selected_facts)} facts")
        log.info(f"  → Reasoning: {reasoning}")
        for fact in selected_facts:
            log.info(f"    • {fact}")
    except json.JSONDecodeError:
        log.warning(f"  ⚠️  Failed to parse selection JSON, using all facts")
        selected_facts = facts_list
        reasoning = "Using all facts due to parse error"

    # STAGE 2: Craft bullet from selected facts only
    log.info(f"  → STAGE 2: Crafting bullet from selected facts")

    selected_facts_text = "\n".join([f"• {fact}" for fact in selected_facts])
    char_limit_text = f"\nIMPORTANT: Keep the bullet under {char_limit} characters." if char_limit else ""

    crafting_prompt = f"""You are a professional resume writer creating an optimized bullet point.

TARGET JOB DESCRIPTION:
{job_description}

SELECTED FACTS TO USE (use ONLY these):
{selected_facts_text}

WHY THESE FACTS: {reasoning}

WRITING GUIDELINES:

1. ACTION VERBS - Use strong ownership language:
   • Strong verbs: Led, Developed, Engineered, Optimized, Architected, Drove, Delivered, Built, Designed, Implemented
   • Match the job description's language level

2. STRUCTURE - Craft one powerful statement:
   • Lead with action verb
   • State the achievement/outcome clearly
   • Include the most impressive metric/result
   • END IMMEDIATELY after the strongest point - don't trail off

3. CONCISENESS - Every word must earn its place:
   • Cut filler: "comprehensive", "utilizing", "leveraging"
   • Don't explain the obvious
   • After stating the result, STOP - no trailing "through X" clauses

4. JD ALIGNMENT - Use terminology from the job description

5. FACTS ONLY - Do NOT add information beyond the selected facts above{char_limit_text}

Return ONLY the new bullet."""

    log.debug(f"  Crafting prompt created, calling Anthropic")

    r2 = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": crafting_prompt}],
        temperature=0.4  # Allow some variety in phrasing
    )

    enhanced_bullet = (r2.content[0].text or "").strip()
    enhanced_bullet = enhanced_bullet.lstrip("-• ").strip()

    log.info(f"  → Scaffolded result: '{enhanced_bullet[:80]}...'")
    log.info(f"  → Generated bullet: {len(enhanced_bullet)} chars")

    return enhanced_bullet


def generate_conversational_question(bullet_text: str) -> str:
    """
    Generate an initial conversational question to start gathering context about a bullet.

    Uses a friendly, interview-style approach rather than formal Q&A.

    Args:
        bullet_text: The original bullet text

    Returns:
        A conversational opening question/prompt
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    system_prompt = """You are a professional resume coach conducting a friendly interview to understand someone's work experience.

Your goal is to help them articulate:
- What they actually did (specific actions, methods, tools)
- The results they achieved (metrics, outcomes, impact)
- The scope and context (team size, budget, scale, timeframe)

Be conversational and encouraging. Ask follow-up questions based on what they share. If they mention something vague, dig deeper for specifics.

Guidelines:
- Ask 1-2 questions at a time, don't overwhelm
- When you get good detail on actions, results, and scope, you can wrap up
- If they seem stuck, give examples: "For instance, did you work with a team? What tools did you use? Any metrics you can share?"
- Keep it natural - you're having a conversation, not interrogating

When you have enough detail for a strong bullet (actions + results + context), say: "Perfect! I have what I need for this one. Let's move on.\""""

    user_prompt = f"""Let's talk about this experience: "{bullet_text}"

Tell me the story - what did this role actually involve? What were you doing day-to-day, and what results did you achieve?"""

    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )

    question = (r.content[0].text or "").strip()
    log.info(f"Generated conversational question for: {bullet_text[:50]}...")
    return question


def extract_facts_from_conversation(bullet_text: str, conversation_history: str) -> Dict:
    """
    Extract structured facts from a conversational exchange about a work experience.

    This is an improved version that handles natural conversation flow.

    Args:
        bullet_text: The original bullet text
        conversation_history: Full conversation as a string (Q&A back and forth)

    Returns:
        Structured facts dictionary with: situation, actions, results, skills, tools, timeline
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    system_prompt = """You are a professional resume expert. Your job is to extract structured facts from a conversation about a work experience.

Extract the following information:
- Situation/Context: What was the scope, scale, or setting?
- Actions: Specific things they did (tools, methods, processes)
- Results: Quantifiable outcomes, metrics, achievements
- Skills: Technical and soft skills demonstrated
- Timeline: When this occurred (if mentioned)

Be specific and preserve numbers. If something wasn't mentioned, omit it rather than guessing.

Output as JSON:
{
  "situation": "string describing scope/context",
  "actions": ["action 1", "action 2"],
  "results": ["result 1 with metrics", "result 2"],
  "skills": ["skill 1", "skill 2"],
  "tools": ["tool 1", "tool 2"],
  "timeline": "when this happened"
}"""

    user_prompt = f"""Original bullet: "{bullet_text}"

Conversation:
{conversation_history}

Extract structured facts from this conversation."""

    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ],
        temperature=0
    )

    raw = (r.content[0].text or "").strip()

    try:
        # Clean potential code fences
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = re.sub(r"^\s*json", "", raw, flags=re.I).strip()

        facts = loads(raw)

        # Ensure all expected keys exist
        default_structure = {
            "situation": "",
            "actions": [],
            "results": [],
            "skills": [],
            "tools": [],
            "timeline": ""
        }

        for key, default_value in default_structure.items():
            if key not in facts:
                facts[key] = default_value

        log.info(f"Extracted facts from conversation for: {bullet_text[:50]}...")
        return facts

    except Exception as e:
        log.exception(f"Failed to parse conversation facts: {e}")
        # Return minimal structure
        return {
            "situation": "",
            "actions": [],
            "results": [],
            "skills": [],
            "tools": [],
            "timeline": ""
        }


# =============================================================================
# EXPERIMENTAL APPROACHES FOR A/B TESTING
# =============================================================================

def _format_facts(stored_facts: Dict) -> str:
    """Helper to format facts dictionary into readable text."""
    facts_text = ""
    if stored_facts.get("situation"):
        facts_text += f"Context: {stored_facts['situation']}\n"
    if stored_facts.get("actions"):
        actions = stored_facts["actions"]
        if isinstance(actions, list) and actions:
            facts_text += "Actions: " + "; ".join(actions) + "\n"
    if stored_facts.get("results"):
        results = stored_facts["results"]
        if isinstance(results, list) and results:
            facts_text += "Results: " + "; ".join(results) + "\n"
    if stored_facts.get("skills"):
        skills = stored_facts["skills"]
        if isinstance(skills, list) and skills:
            facts_text += f"Skills: {', '.join(skills)}\n"
    if stored_facts.get("tools"):
        tools = stored_facts["tools"]
        if isinstance(tools, list) and tools:
            facts_text += f"Tools: {', '.join(tools)}\n"
    if stored_facts.get("timeline"):
        facts_text += f"Timeline: {stored_facts['timeline']}\n"
    return facts_text.strip()


def generate_bullet_self_critique(original_bullet: str, job_description: str,
                                   stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Self-Critique Loop: Generate -> Critique -> Revise
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    has_facts = bool(stored_facts and any(stored_facts.get(c) for c in ["tools", "skills", "actions", "results", "situation", "timeline"]))
    facts_text = _format_facts(stored_facts) if has_facts else ""
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""

    log.info(f"generate_bullet_self_critique - '{original_bullet[:50]}...'")

    # STAGE 1: Generate
    if has_facts:
        gen_prompt = f"""Optimize this bullet for the job using verified facts.

ORIGINAL: {original_bullet}
JD: {job_description}
FACTS: {facts_text}

Write one optimized bullet with strong verb, best metric, JD alignment.{char_text}
Return ONLY the bullet."""
    else:
        gen_prompt = f"""Optimize this bullet for the job. PRESERVE all original facts - add nothing new.

ORIGINAL: {original_bullet}
JD: {job_description}

Strengthen verb, improve structure, align terminology.{char_text}
Return ONLY the bullet."""

    r1 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": gen_prompt}], temperature=0.4)
    draft = (r1.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Draft: '{draft[:60]}...'")

    # STAGE 2: Critique
    critique_prompt = f"""You're a hiring manager. Critique this bullet for this role.

JD: {job_description}
BULLET: {draft}

List 2-3 specific improvements needed (relevance, impact clarity, verb strength, conciseness, ending)."""

    r2 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": critique_prompt}], temperature=0.2)
    critique = (r2.content[0].text or "").strip()
    log.info(f"  Critique: '{critique[:60]}...'")

    # STAGE 3: Revise
    revise_prompt = f"""Revise this bullet based on the critique.

BULLET: {draft}
CRITIQUE: {critique}
{"FACTS: " + facts_text if has_facts else "IMPORTANT: Add nothing not in original."}

Address each point.{char_text}
Return ONLY the revised bullet."""

    r3 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": revise_prompt}], temperature=0.3)
    final = (r3.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Final: '{final[:60]}...'")
    return final


def generate_bullet_multi_candidate(original_bullet: str, job_description: str,
                                     stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Multi-Candidate: Generate 3 variants -> Select best
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    has_facts = bool(stored_facts and any(stored_facts.get(c) for c in ["tools", "skills", "actions", "results", "situation", "timeline"]))
    facts_text = _format_facts(stored_facts) if has_facts else ""
    char_text = f"\nEach under {char_limit} chars." if char_limit else ""

    log.info(f"generate_bullet_multi_candidate - '{original_bullet[:50]}...'")

    # STAGE 1: Generate 3 candidates
    if has_facts:
        gen_prompt = f"""Generate 3 DIFFERENT bullet versions for this job.

ORIGINAL: {original_bullet}
JD: {job_description}
FACTS: {facts_text}

Make each distinct: different verbs, structures (impact-first vs action-first), emphasis (skills vs results vs leadership).{char_text}

VERSION 1: [bullet]
VERSION 2: [bullet]
VERSION 3: [bullet]"""
    else:
        gen_prompt = f"""Generate 3 DIFFERENT bullet versions. PRESERVE all original facts.

ORIGINAL: {original_bullet}
JD: {job_description}

Make each distinct: different verbs, structures, emphasis.{char_text}

VERSION 1: [bullet]
VERSION 2: [bullet]
VERSION 3: [bullet]"""

    r1 = client.messages.create(model=CHAT_MODEL, max_tokens=1024, messages=[{"role": "user", "content": gen_prompt}], temperature=0.7)
    candidates = (r1.content[0].text or "").strip()
    log.info(f"  Generated 3 candidates")

    # STAGE 2: Select best
    select_prompt = f"""You're hiring for this role. Pick the BEST bullet.

JD: {job_description}

CANDIDATES:
{candidates}

Evaluate: relevance, impact clarity, language strength, conciseness.
Return ONLY the winning bullet text (no "VERSION X:", just the bullet)."""

    r2 = client.messages.create(model=CHAT_MODEL, max_tokens=256, messages=[{"role": "user", "content": select_prompt}], temperature=0)
    selected = (r2.content[0].text or "").strip().lstrip("-• ")
    for prefix in ["VERSION 1:", "VERSION 2:", "VERSION 3:", "Winner:", "Best:"]:
        if selected.upper().startswith(prefix.upper()):
            selected = selected[len(prefix):].strip()
    log.info(f"  Selected: '{selected[:60]}...'")
    return selected


def generate_bullet_hiring_manager(original_bullet: str, job_description: str,
                                    stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Hiring Manager Perspective: Write as the evaluator
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    has_facts = bool(stored_facts and any(stored_facts.get(c) for c in ["tools", "skills", "actions", "results", "situation", "timeline"]))
    facts_text = _format_facts(stored_facts) if has_facts else ""
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""

    log.info(f"generate_bullet_hiring_manager - '{original_bullet[:50]}...'")

    system = """You're an experienced hiring manager. You know what makes bullets stand out:
- Specific beats vague
- Numbers catch the eye
- Strong verbs show ownership (Led, Built, Drove) vs weak (Helped, Assisted)
- Relevance to job trumps impressiveness
- Concise gets read; long gets skimmed
- End strong, don't trail off"""

    if has_facts:
        user = f"""I'm hiring for:
{job_description}

Candidate experience:
ORIGINAL: {original_bullet}
DETAILS: {facts_text}

Rewrite so I'd want to interview them. Use only verified details.{char_text}
Return ONLY the bullet."""
    else:
        user = f"""I'm hiring for:
{job_description}

Candidate bullet:
{original_bullet}

Rewrite so I'd want to interview them. ONLY use info from original - add nothing.{char_text}
Return ONLY the bullet."""

    r = client.messages.create(model=CHAT_MODEL, max_tokens=512, system=system, messages=[{"role": "user", "content": user}], temperature=0.4)
    result = (r.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def generate_bullet_jd_mirror(original_bullet: str, job_description: str,
                               stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    JD-Mirroring: Extract JD phrases -> Incorporate them
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    has_facts = bool(stored_facts and any(stored_facts.get(c) for c in ["tools", "skills", "actions", "results", "situation", "timeline"]))
    facts_text = _format_facts(stored_facts) if has_facts else ""
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""

    log.info(f"generate_bullet_jd_mirror - '{original_bullet[:50]}...'")

    # STAGE 1: Extract JD phrases
    extract_prompt = f"""Extract 3-5 specific JD phrases matching the candidate's experience.

JD: {job_description}

EXPERIENCE: {original_bullet}
{("DETAILS: " + facts_text) if has_facts else ""}

Return phrases (one per line) that:
- Match candidate's demonstrated skills/actions
- Are specific (not "team player")
- Help ATS matching"""

    r1 = client.messages.create(model=CHAT_MODEL, max_tokens=256, messages=[{"role": "user", "content": extract_prompt}], temperature=0)
    phrases = (r1.content[0].text or "").strip()
    log.info(f"  JD phrases: '{phrases[:60]}...'")

    # STAGE 2: Rewrite with phrases
    if has_facts:
        rewrite = f"""Rewrite to naturally incorporate JD phrases.

ORIGINAL: {original_bullet}
JD PHRASES: {phrases}
FACTS: {facts_text}

Use 2-3 phrases naturally. Strong verb, best metric.{char_text}
Return ONLY the bullet."""
    else:
        rewrite = f"""Rewrite to naturally incorporate JD phrases.

ORIGINAL: {original_bullet}
JD PHRASES: {phrases}

Use 2-3 phrases naturally. PRESERVE original facts - add nothing new.{char_text}
Return ONLY the bullet."""

    r2 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": rewrite}], temperature=0.3)
    result = (r2.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result

