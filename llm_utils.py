import re, hashlib, json
from json import loads
from typing import List, Dict, Optional, Tuple
from config import client, async_client, openai_client, CHAT_MODEL, EMBED_MODEL, USE_DISTILLED_JD, USE_LLM_TERMS, log
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

    prompt = f"""You are a resume writer who NEVER invents information.

ORIGINAL BULLET:
{original_bullet}

TARGET JOB DESCRIPTION:
{job_description}

YOUR TASK: Reword this bullet to better align with the job description.

⚠️ CRITICAL CONSTRAINT - READ THIS FIRST:
You can ONLY use information that appears in the original bullet above.
- If the original has no metrics, your output has no metrics
- If the original has no specific tools, your output has no specific tools
- If the original doesn't match the job well, that's OK - do your best without lying

WHAT YOU CAN CHANGE:
✓ Strengthen weak verbs ("helped with" → "supported", "worked on" → "contributed to")
✓ Reorder for impact (lead with the most relevant part)
✓ Swap synonyms to match JD terminology (if meaning is identical)
✓ Tighten wordiness

WHAT YOU CANNOT DO:
✗ Add numbers, metrics, or percentages not in original
✗ Add tools, technologies, or methodologies not in original
✗ Add team sizes, timelines, or scope not in original
✗ Infer or imply details beyond what's explicitly stated
✗ Make vague claims specific (if original says "improved", don't add "by 30%")

ACCEPT LIMITATIONS: If the bullet doesn't align well with this job, produce the best honest version. A modest truthful bullet beats an impressive lie.
{char_limit_text}
Return ONLY the reworded bullet. No explanation."""

    try:
        log.debug(f"  Calling Anthropic with temperature=0.2")
        response = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2  # Low temperature to reduce creativity/hallucination
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

    prompt = f"""You are a resume writer who NEVER invents information.

TARGET JOB DESCRIPTION:
{job_description}

VERIFIED FACTS (your ONLY source material):
{facts_text}

⚠️ CRITICAL CONSTRAINT - READ THIS FIRST:
You can ONLY use information from the VERIFIED FACTS above.
- Every metric in your output must appear in the facts
- Every tool/technology must appear in the facts
- Every claim must be directly traceable to the facts
- Do NOT add anything "implied" or "likely" - only explicit facts

FORMAT: Use Google's XYZ structure (vary your phrasing, not literal every time):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it (methods, tools, approach)
Good examples: "Reduced costs 20% by automating...", "Led team of 8 to deliver...", "Built pipeline processing 1M records using..."

ACCEPT LIMITATIONS: If these facts don't align well with the job, that's OK.
Write the best honest bullet you can. A modest truthful bullet beats an impressive lie.
{char_limit_text}
Return ONLY the bullet. No explanation."""

    # Log the full prompt so it's visible in logs
    log.info(f"  ===== WITH-FACTS PROMPT START =====")
    log.info(prompt)
    log.info(f"  ===== WITH-FACTS PROMPT END =====")

    log.debug(f"  Calling Anthropic with temperature=0.2")
    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2  # Low to reduce hallucination
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

    crafting_prompt = f"""You are a resume writer who NEVER invents information.

SELECTED FACTS (your ONLY source - use nothing else):
{selected_facts_text}

TARGET JOB DESCRIPTION:
{job_description}

⚠️ CRITICAL: You can ONLY use information from the SELECTED FACTS above.
- Every metric must come from the facts
- Every tool/skill must come from the facts
- Do NOT add anything implied or assumed

FORMAT: Use Google's XYZ structure (vary your phrasing, not literal every time):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it (methods, tools, approach)
Good examples: "Reduced costs 20% by automating...", "Led team of 8 to deliver...", "Built pipeline processing 1M records using..."

ACCEPT LIMITATIONS: If these facts don't match the job well, write the best honest bullet you can. A modest truthful bullet beats an impressive lie.
{char_limit_text}
Return ONLY the bullet."""

    log.debug(f"  Crafting prompt created, calling Anthropic")

    r2 = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": crafting_prompt}],
        temperature=0.2  # Low to reduce hallucination
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
    source = f"VERIFIED FACTS:\n{facts_text}" if has_facts else f"ORIGINAL BULLET:\n{original_bullet}"

    log.info(f"generate_bullet_self_critique - '{original_bullet[:50]}...'")

    # STAGE 1: Generate
    gen_prompt = f"""You are a resume writer who NEVER invents information.

{source}

JOB DESCRIPTION:
{job_description}

FORMAT: Use Google's XYZ structure (vary your phrasing, not literal every time):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it (methods, tools, approach)
Good examples: "Reduced costs 20% by automating...", "Led team of 8 to deliver...", "Built pipeline processing 1M records using..."

TOOLS: Only mention tools that are:
- Technical differentiators (Python, Tableau, Snowflake, etc.)
- Explicitly mentioned in the JD
- Essential to understanding the achievement
OMIT basic tools: Excel, pivot tables, Word, PowerPoint, email, "various tools"

CONCISENESS: Cut filler ruthlessly.
- Use tool names directly: "SQL" not "SQL-based data extraction"
- Cut meaningless phrases: "data-driven strategies", "leveraging insights", "utilizing methodologies"
- Every word must earn its place - if removing it doesn't lose meaning, remove it

⚠️ CONSTRAINT: Use ONLY information from the source above. Add nothing.
If fit is poor, that's OK - write the best honest bullet you can.
{char_text}
Return ONLY the bullet."""

    r1 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": gen_prompt}], temperature=0.2)
    draft = (r1.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Draft: '{draft[:60]}...'")

    # STAGE 2: Critique (focus on HONESTY not impressiveness)
    critique_prompt = f"""Review this bullet for FACTUAL ACCURACY first, then quality.

SOURCE MATERIAL:
{source}

BULLET TO REVIEW:
{draft}

Check:
1. Does the bullet contain ANY information not in the source? (This is a failure)
2. Does it follow XYZ structure (accomplishment + result + method)? Phrasing can vary.
3. Is it relevant to the job?
4. Is it concise? Flag verbose filler like:
   - "SQL-based data extraction" (should be "SQL")
   - "data-driven strategies", "leveraging insights", "utilizing methodologies"
   - Any phrase that can be cut without losing meaning

List specific issues. If it added information not in source, that's the #1 problem."""

    r2 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": critique_prompt}], temperature=0.1)
    critique = (r2.content[0].text or "").strip()
    log.info(f"  Critique: '{critique[:60]}...'")

    # STAGE 3: Revise
    revise_prompt = f"""Revise this bullet based on the critique.

BULLET: {draft}
CRITIQUE: {critique}

SOURCE (your ONLY allowed information):
{source}

FORMAT: Use Google's XYZ structure (vary your phrasing):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it

⚠️ If critique says you added information, REMOVE IT. Only use source material.
A modest honest bullet beats an impressive lie.
{char_text}
Return ONLY the revised bullet."""

    r3 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": revise_prompt}], temperature=0.2)
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
    source = f"VERIFIED FACTS:\n{facts_text}" if has_facts else f"ORIGINAL BULLET:\n{original_bullet}"

    log.info(f"generate_bullet_multi_candidate - '{original_bullet[:50]}...'")

    # STAGE 1: Generate 3 candidates
    gen_prompt = f"""You are a resume writer who NEVER invents information.

{source}

JOB DESCRIPTION:
{job_description}

FORMAT: Use Google's XYZ structure (vary your phrasing across versions):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it (methods, tools, approach)

⚠️ CONSTRAINT: Each version can ONLY use information from the source above.
- No added metrics, tools, or details
- If fit is poor, that's OK - write honest variations

Generate 3 different versions (vary structure, emphasis, and phrasing - NOT facts):
{char_text}
VERSION 1: [bullet]
VERSION 2: [bullet]
VERSION 3: [bullet]"""

    r1 = client.messages.create(model=CHAT_MODEL, max_tokens=1024, messages=[{"role": "user", "content": gen_prompt}], temperature=0.3)
    candidates = (r1.content[0].text or "").strip()
    log.info(f"  Generated 3 candidates")

    # STAGE 2: Select best (prioritize honesty)
    select_prompt = f"""Pick the BEST bullet from these candidates.

SOURCE MATERIAL (what the bullet should be based on):
{source}

CANDIDATES:
{candidates}

Evaluate:
1. FACTUAL ACCURACY - Does it only contain info from the source? (Most important)
2. Relevance to job
3. Conciseness

Return ONLY the winning bullet text (no "VERSION X:")."""

    r2 = client.messages.create(model=CHAT_MODEL, max_tokens=256, messages=[{"role": "user", "content": select_prompt}], temperature=0)
    selected = (r2.content[0].text or "").strip().lstrip("-• ")
    for prefix in ["VERSION 1:", "VERSION 2:", "VERSION 3:", "Winner:", "Best:"]:
        if selected.upper().startswith(prefix.upper()):
            selected = selected[len(prefix):].strip()
    log.info(f"  Selected: '{selected[:60]}...'")
    return selected


def optimize_keywords_factual_first(original_bullet: str, job_description: str,
                                     stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Factual-First Keyword Optimization: Preserve facts as a hard constraint.

    This approach treats factual accuracy as non-negotiable:
    1. Only allows synonym swaps where meanings are IDENTICAL
    2. Never adds claims, tools, metrics, or qualifiers not in original
    3. If unsure, keeps original wording
    4. Keyword improvement is secondary to factual preservation
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_factual_first - '{original_bullet[:50]}...'")
    char_text = f"Stay under {char_limit} characters." if char_limit else ""

    prompt = f"""You are optimizing a resume bullet for ATS keyword matching.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

YOUR TASK: Make MINIMAL changes to incorporate relevant keywords from the job description.

STRICT RULES (VIOLATIONS ARE UNACCEPTABLE):
1. NEVER add tools, technologies, or skills not explicitly mentioned in the original (e.g., don't add "SQL", "Python", "Tableau" unless the original already mentions them)
2. NEVER add metrics, numbers, or quantifications not in the original
3. NEVER add qualifiers like "evidence-based", "data-driven", "cross-functional" unless the original already uses them
4. NEVER change the core action or achievement described
5. NEVER invent context or expand scope beyond what's stated

ALLOWED CHANGES (USE SPARINGLY):
- Swap a word for a JD synonym with IDENTICAL meaning (e.g., "conducted analysis" → "performed analysis")
- Reorder words slightly if it doesn't change meaning
- Minor phrasing adjustments that preserve exact meaning

IF IN DOUBT: Keep the original wording. A missed keyword is better than a fabricated claim.

{char_text}

Return ONLY the optimized bullet, nothing else."""

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    result = (response.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def optimize_keywords_synonym_only(original_bullet: str, job_description: str,
                                    stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Synonym-Only: ONLY allows 1:1 word swaps where meanings are identical.

    This is the most conservative approach - no rephrasing, no additions,
    just direct synonym swaps where the JD uses a different word for the same concept.
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_synonym_only - '{original_bullet[:50]}...'")
    char_text = f"Stay under {char_limit} characters." if char_limit else ""

    prompt = f"""Find words in this bullet that can be swapped with EXACT synonyms from the job description.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

RULES:
1. ONLY swap a word if the JD uses a different word with the EXACT SAME meaning
2. Examples of valid swaps:
   - "conducted" → "performed" (same meaning)
   - "built" → "developed" (same meaning)
   - "customers" → "users" (same meaning if context fits)
3. Examples of INVALID swaps (DO NOT DO):
   - "analysis" → "market research and competitive analysis" (adding words)
   - "planning" → "strategic planning" (adding qualifier)
   - Adding any word that wasn't there before
4. If no valid synonym swaps exist, return the original bullet unchanged
5. Maximum 2-3 word swaps per bullet

{char_text}

Return ONLY the bullet (original or with swaps), nothing else."""

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    result = (response.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def optimize_keywords_light_touch(original_bullet: str, job_description: str,
                                   stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Light Touch: Small adjustments allowed, but with explicit guardrails.

    Allows minor rephrasing beyond pure synonyms, but with a clear list of
    what is and isn't allowed.
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_light_touch - '{original_bullet[:50]}...'")
    char_text = f"Stay under {char_limit} characters." if char_limit else ""

    prompt = f"""Make small adjustments to align this bullet with the job description keywords.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

ALLOWED (small adjustments):
✓ Swap synonyms (e.g., "built" → "developed")
✓ Reorder words slightly if meaning unchanged
✓ Use JD phrasing for concepts already present (e.g., if bullet says "talked to users" and JD says "user research", can say "conducted user research" IF the bullet already describes research activities)

FORBIDDEN (these invalidate the bullet):
✗ Adding tools/technologies not mentioned (SQL, Python, Tableau, etc.)
✗ Adding metrics or numbers not in original
✗ Adding audiences not mentioned (stakeholders, leadership, clients)
✗ Adding qualifiers that change scope (cross-functional, enterprise-wide, etc.)
✗ Adding deliverables not mentioned (frameworks, models, recommendations)
✗ Changing what was actually done

GOAL: A hiring manager reading both versions should believe they describe the exact same work.

{char_text}

Return ONLY the adjusted bullet, nothing else."""

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    result = (response.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def optimize_keywords_one_change(original_bullet: str, job_description: str,
                                  stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    One Change Only: Make exactly ONE keyword improvement, the safest one.

    Forces the model to pick the single best, safest keyword swap rather
    than trying to optimize everything at once.
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_one_change - '{original_bullet[:50]}...'")
    char_text = f"Stay under {char_limit} characters." if char_limit else ""

    prompt = f"""Make exactly ONE small change to add a keyword from the job description.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

INSTRUCTIONS:
1. Find the ONE safest word swap or minor adjustment that adds a JD keyword
2. The change must not alter the meaning of what was done
3. If you can't find a safe change, return the original unchanged

Examples of safe single changes:
- "conducted analysis" → "conducted market analysis" (if analysis was of a market)
- "built framework" → "developed framework" (verb swap)
- "informed decisions" → "informed strategic decisions" (if decisions were strategic)

DO NOT:
- Add tools, metrics, or audiences not in the original
- Make multiple changes
- Change what was actually accomplished

{char_text}

Return ONLY the bullet with your one change (or original if no safe change), nothing else."""

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    result = (response.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def deduplicate_repeated_words(optimized_bullets: List[str], job_description: str) -> List[str]:
    """
    Post-process a list of optimized bullets to remove repetitive vocabulary.

    This addresses the problem where optimizing bullets individually can lead to
    the same action verbs appearing too frequently across the resume.

    Args:
        optimized_bullets: List of bullets that have already been optimized
        job_description: Job description to maintain keyword alignment

    Returns:
        List of bullets with diversified vocabulary while maintaining facts and keywords
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    if len(optimized_bullets) <= 1:
        # No deduplication needed for single bullet
        return optimized_bullets

    log.info(f"deduplicate_repeated_words - Processing {len(optimized_bullets)} bullets")

    # Format bullets with numbers for clarity
    bullets_text = "\n".join(f"{i+1}. {bullet}" for i, bullet in enumerate(optimized_bullets))

    prompt = f"""These resume bullets were independently optimized and now have repetitive vocabulary.
Please diversify the action verbs and phrasing while maintaining ALL facts and keyword alignment.

JOB DESCRIPTION (maintain alignment with these keywords):
{job_description}

CURRENT BULLETS (notice repetitive words):
{bullets_text}

RULES:
1. Keep ALL facts, metrics, tools, and accomplishments exactly as stated
2. Vary action verbs across bullets (if "generated" appears multiple times, use "developed", "created", "built" in other bullets)
3. Maintain keyword alignment with job description
4. Do NOT add new information, metrics, or claims
5. Do NOT remove any factual content

GOAL: Same factual content, same keyword optimization, but more varied vocabulary.

Return the improved bullets in the SAME ORDER, one per line, numbered 1-{len(optimized_bullets)}."""

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=2048,  # Enough for multiple bullets
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3  # Slight creativity for variety, but still conservative
    )

    result_text = (response.content[0].text or "").strip()

    # Parse the response back into a list
    # Handle numbered format: "1. Bullet text\n2. Bullet text..."
    lines = result_text.split('\n')
    deduplicated = []

    for line in lines:
        # Strip number prefix if present (e.g., "1. " or "1) ")
        cleaned = re.sub(r'^\s*\d+[\.\)]\s*', '', line).strip().lstrip("-• ")
        if cleaned:  # Only add non-empty lines
            deduplicated.append(cleaned)

    # Fallback: if parsing failed, return original
    if len(deduplicated) != len(optimized_bullets):
        log.warning(f"Deduplication parsing failed: expected {len(optimized_bullets)} bullets, got {len(deduplicated)}. Using original.")
        return optimized_bullets

    log.info(f"Deduplication complete - {len(deduplicated)} bullets diversified")

    return deduplicated


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
    source = f"VERIFIED FACTS:\n{facts_text}" if has_facts else f"ORIGINAL BULLET:\n{original_bullet}"

    log.info(f"generate_bullet_hiring_manager - '{original_bullet[:50]}...'")

    system = """You're an experienced hiring manager who VALUES HONESTY over impressiveness.

You know:
- A candidate who embellishes is a red flag
- Modest but verifiable beats impressive but vague
- You'd rather see "Analyzed data" than "Leveraged advanced analytics to drive strategic insights"
- Specifics from the actual work matter more than buzzwords"""

    user = f"""I'm hiring for:
{job_description}

Candidate's VERIFIED information (this is ALL you can use):
{source}

FORMAT: Use XYZ structure (vary phrasing naturally):
- What they accomplished + measurable result (if available) + how they did it
- Examples: "Reduced costs 20% by automating...", "Led team of 8 to deliver...", "Built pipeline processing 1M records using..."

Rewrite as a bullet I'd trust. Use ONLY the information above - add nothing.
If their experience doesn't match my job well, that's fine - I prefer an honest modest bullet over an impressive fake one.
{char_text}
Return ONLY the bullet."""

    r = client.messages.create(model=CHAT_MODEL, max_tokens=512, system=system, messages=[{"role": "user", "content": user}], temperature=0.2)
    result = (r.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def generate_bullet_jd_mirror(original_bullet: str, job_description: str,
                               stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    JD-Mirroring: Extract JD phrases -> Incorporate them (without adding facts)
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    has_facts = bool(stored_facts and any(stored_facts.get(c) for c in ["tools", "skills", "actions", "results", "situation", "timeline"]))
    facts_text = _format_facts(stored_facts) if has_facts else ""
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""
    source = f"VERIFIED FACTS:\n{facts_text}" if has_facts else f"ORIGINAL BULLET:\n{original_bullet}"

    log.info(f"generate_bullet_jd_mirror - '{original_bullet[:50]}...'")

    # STAGE 1: Extract JD phrases that MATCH existing experience
    extract_prompt = f"""Find JD terminology that matches the candidate's ACTUAL experience.

JOB DESCRIPTION:
{job_description}

CANDIDATE'S VERIFIED EXPERIENCE:
{source}

List 2-4 JD phrases where the candidate has DEMONSTRATED that skill/action.
Only include phrases where there's a real match - don't stretch.
If few phrases match, that's OK - list only genuine matches."""

    r1 = client.messages.create(model=CHAT_MODEL, max_tokens=256, messages=[{"role": "user", "content": extract_prompt}], temperature=0)
    phrases = (r1.content[0].text or "").strip()
    log.info(f"  JD phrases: '{phrases[:60]}...'")

    # STAGE 2: Rewrite using ONLY source facts, with JD terminology where it fits
    rewrite = f"""Rewrite using JD terminology where it naturally fits.

SOURCE (your ONLY allowed information):
{source}

JD PHRASES TO USE (only if they fit naturally):
{phrases}

FORMAT: Use Google's XYZ structure (vary your phrasing):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it (methods, tools, approach)

⚠️ CONSTRAINT:
- You can swap synonyms (e.g., "built" → "developed" if JD uses "developed")
- You CANNOT add new information, metrics, or claims
- If a JD phrase doesn't fit the actual experience, don't force it

A modest honest bullet with some JD keywords beats an impressive lie.
{char_text}
Return ONLY the bullet."""

    r2 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": rewrite}], temperature=0.2)
    result = (r2.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def generate_bullet_combined(original_bullet: str, job_description: str,
                              stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Combined Multi-Candidate + Self-Critique:
    1. Generate 3 candidate bullets
    2. Critique each for factual accuracy
    3. Select the best one that passes factual check

    This combines the creativity of multi-candidate with the factual rigor of self-critique.
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    has_facts = bool(stored_facts and any(stored_facts.get(c) for c in ["tools", "skills", "actions", "results", "situation", "timeline"]))
    facts_text = _format_facts(stored_facts) if has_facts else ""
    char_text = f"\nEach under {char_limit} chars." if char_limit else ""
    source = f"VERIFIED FACTS:\n{facts_text}" if has_facts else f"ORIGINAL BULLET:\n{original_bullet}"

    log.info(f"generate_bullet_combined - '{original_bullet[:50]}...'")

    # STAGE 1: Generate 3 candidates (same as multi_candidate)
    gen_prompt = f"""You are a resume writer who NEVER invents information.

{source}

JOB DESCRIPTION:
{job_description}

FORMAT: Use Google's XYZ structure (vary your phrasing across versions):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it (methods, tools, approach)

⚠️ CONSTRAINT: Each version can ONLY use information from the source above.
- No added metrics, tools, or details
- If fit is poor, that's OK - write honest variations

Generate 3 different versions (vary structure, emphasis, and phrasing - NOT facts):
{char_text}
VERSION 1: [bullet]
VERSION 2: [bullet]
VERSION 3: [bullet]"""

    r1 = client.messages.create(model=CHAT_MODEL, max_tokens=1024, messages=[{"role": "user", "content": gen_prompt}], temperature=0.3)
    candidates_raw = (r1.content[0].text or "").strip()
    log.info(f"  Generated 3 candidates")

    # STAGE 2: Critique ALL candidates for factual accuracy
    critique_prompt = f"""Review these 3 bullet candidates for FACTUAL ACCURACY.

SOURCE MATERIAL (the ONLY allowed information):
{source}

CANDIDATES:
{candidates_raw}

For EACH candidate, check:
1. Does it contain ANY information not in the source? (CRITICAL FAILURE)
2. Does it add metrics, tools, or details not in source? (FAILURE)
3. Is it relevant to job and concise? (Quality check)

Score each 1-5 on factual accuracy (5 = perfectly faithful, 1 = fabricates information).
Return as:
VERSION 1: [score] - [brief reason]
VERSION 2: [score] - [brief reason]
VERSION 3: [score] - [brief reason]
BEST: [version number]"""

    r2 = client.messages.create(model=CHAT_MODEL, max_tokens=512, messages=[{"role": "user", "content": critique_prompt}], temperature=0)
    critique = (r2.content[0].text or "").strip()
    log.info(f"  Critique: '{critique[:100]}...'")

    # STAGE 3: Revise the best candidate based on critique
    revise_prompt = f"""Based on the critique, select and refine the best bullet.

CANDIDATES:
{candidates_raw}

CRITIQUE:
{critique}

SOURCE (your ONLY allowed information):
{source}

Take the version with highest factual accuracy score.
If it had any issues noted, fix them by REMOVING fabricated information (not adding more).
A modest honest bullet beats an impressive lie.
{char_text}
Return ONLY the final refined bullet."""

    r3 = client.messages.create(model=CHAT_MODEL, max_tokens=256, messages=[{"role": "user", "content": revise_prompt}], temperature=0.1)
    final = (r3.content[0].text or "").strip().lstrip("-• ")

    # Clean up any version prefixes
    for prefix in ["VERSION 1:", "VERSION 2:", "VERSION 3:", "Winner:", "Best:", "FINAL:"]:
        if final.upper().startswith(prefix.upper()):
            final = final[len(prefix):].strip()

    log.info(f"  Final: '{final[:60]}...'")
    return final


def generate_bullets_batch(bullets_data: List[Dict], job_description: str,
                           char_limit: Optional[int] = None) -> List[str]:
    """
    Batch Bullet Processing: Process multiple bullets together for coherent output.

    This approach:
    1. Sees all bullets at once for context
    2. Ensures variety across bullets (no repetitive phrasing)
    3. Strategically distributes keywords across the set

    Args:
        bullets_data: List of dicts with 'original_bullet' and 'stored_facts' keys
        job_description: Target job description
        char_limit: Optional character limit per bullet

    Returns:
        List of enhanced bullets in same order as input
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    if not bullets_data:
        return []

    log.info(f"generate_bullets_batch - Processing {len(bullets_data)} bullets together")

    # Format all bullets with their facts
    bullets_formatted = []
    for i, item in enumerate(bullets_data, 1):
        original = item.get("original_bullet", "")
        facts = item.get("stored_facts", {})
        has_facts = bool(facts and any(facts.get(c) for c in ["tools", "skills", "actions", "results", "situation", "timeline"]))

        if has_facts:
            facts_text = _format_facts(facts)
            bullets_formatted.append(f"BULLET {i}:\nOriginal: {original}\nFacts: {facts_text}")
        else:
            bullets_formatted.append(f"BULLET {i}:\nOriginal: {original}\nFacts: (none - preserve original information)")

    bullets_section = "\n\n".join(bullets_formatted)
    char_text = f"\nKeep each bullet under {char_limit} characters." if char_limit else ""

    # Single-stage batch generation with coherence instructions
    batch_prompt = f"""You are a resume writer optimizing a SET of bullets together. NEVER invent information.

JOB DESCRIPTION:
{job_description}

BULLETS TO OPTIMIZE:
{bullets_section}

FORMAT: Use Google's XYZ structure (vary phrasing across bullets):
- X = What you accomplished/delivered
- Y = Measurable result/impact (only if in source!)
- Z = How you did it (methods, tools, approach)
Good examples: "Reduced costs 20% by automating...", "Led team of 8 to deliver...", "Built pipeline processing 1M records using..."

⚠️ CRITICAL CONSTRAINTS:
- For each bullet, use ONLY the facts provided (or original if no facts)
- Do NOT add metrics, tools, or details not in the source
- If a bullet doesn't fit the job well, write the best honest version

BATCH OPTIMIZATION GOALS:
1. Vary sentence structures and XYZ phrasing across bullets (don't start all with same pattern)
2. Distribute JD keywords strategically (don't repeat same keywords in every bullet)
3. Lead with strongest/most relevant bullets' content
4. Ensure each bullet stands alone but together tells a cohesive story
{char_text}

Return exactly {len(bullets_data)} bullets, numbered:
1. [bullet]
2. [bullet]
...

Return ONLY the numbered bullets, no commentary."""

    r = client.messages.create(model=CHAT_MODEL, max_tokens=2048, messages=[{"role": "user", "content": batch_prompt}], temperature=0.2)
    response = (r.content[0].text or "").strip()

    # Parse numbered bullets from response
    enhanced_bullets = []
    lines = response.split("\n")
    current_bullet = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check if line starts with a number
        match = re.match(r'^(\d+)[.):]\s*(.+)$', line)
        if match:
            if current_bullet:
                enhanced_bullets.append(current_bullet.lstrip("-• "))
            current_bullet = match.group(2)
        elif current_bullet:
            # Continuation of previous bullet
            current_bullet += " " + line

    # Don't forget the last bullet
    if current_bullet:
        enhanced_bullets.append(current_bullet.lstrip("-• "))

    # Ensure we have the right number of bullets
    while len(enhanced_bullets) < len(bullets_data):
        # Fallback: use original bullet
        idx = len(enhanced_bullets)
        enhanced_bullets.append(bullets_data[idx].get("original_bullet", ""))
        log.warning(f"  Bullet {idx+1} missing from batch response, using original")

    # Trim if we got too many
    enhanced_bullets = enhanced_bullets[:len(bullets_data)]

    for i, bullet in enumerate(enhanced_bullets):
        log.info(f"  Bullet {i+1}: '{bullet[:60]}...'")

    return enhanced_bullets


def generate_bullet_batch_wrapper(original_bullet: str, job_description: str,
                                   stored_facts: Dict, char_limit: Optional[int] = None,
                                   _batch_context: Optional[Dict] = None) -> str:
    """
    Wrapper for batch processing that works with the single-bullet evaluation interface.

    For proper batch processing, call generate_bullets_batch directly.
    This wrapper exists for API compatibility with the evaluation framework.

    When _batch_context is provided, it uses pre-computed batch results.
    Otherwise, it processes the single bullet (losing batch benefits).
    """
    if _batch_context and original_bullet in _batch_context:
        return _batch_context[original_bullet]

    # Fallback: process single bullet (not ideal, but maintains compatibility)
    bullets_data = [{"original_bullet": original_bullet, "stored_facts": stored_facts}]
    results = generate_bullets_batch(bullets_data, job_description, char_limit)
    return results[0] if results else original_bullet


# =============================================================================
# KEYWORD-ONLY OPTIMIZATION APPROACHES
# =============================================================================

def optimize_keywords_simple(original_bullet: str, job_description: str,
                             stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Simple Keyword Optimization: Swap synonyms with JD terminology.

    This is the most conservative approach:
    - Keep bullet structure exactly the same
    - Only swap words with synonyms from the JD
    - Do NOT change meaning, just terminology
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_simple - '{original_bullet[:50]}...'")
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""

    prompt = f"""You are optimizing a resume bullet for ATS keyword matching.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

YOUR TASK: Swap words with synonyms from the job description.

RULES:
1. PRESERVE the exact structure and meaning of the bullet
2. ONLY swap words that have exact synonyms in the JD
3. Do NOT add new information, metrics, or claims
4. Do NOT change action verbs unless there's an exact synonym in JD
5. Do NOT restructure the sentence
6. Keep all original facts, numbers, and specifics exactly as they are

EXAMPLES of acceptable swaps:
- "built" → "developed" (if JD uses "developed")
- "analyzed" → "assessed" (if JD uses "assessed")
- "customers" → "clients" (if JD uses "clients")
- "improved" → "optimized" (if JD uses "optimized")

EXAMPLES of unacceptable changes:
- Adding "cross-functional" when not in original
- Adding percentages or metrics
- Changing "helped with" to "led" (that changes meaning)
- Adding technologies not mentioned in original
{char_text}
Return ONLY the optimized bullet with keyword swaps. No explanation."""

    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1  # Very low - we want minimal creativity
    )

    result = (r.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def optimize_keywords_targeted(original_bullet: str, job_description: str,
                               stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Targeted Keyword Optimization: Extract JD keywords first, then inject.

    Two-stage approach:
    1. Extract key terms from JD that could apply to this bullet
    2. Inject those terms while preserving meaning
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_targeted - '{original_bullet[:50]}...'")
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""

    # STAGE 1: Extract relevant JD keywords for this specific bullet
    extract_prompt = f"""Identify JD keywords that could naturally fit this bullet.

BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

List 3-5 specific keywords/phrases from the JD that:
1. Are relevant to what this bullet describes
2. Could replace or supplement existing words
3. Are ATS-important (skills, tools, methodologies, domains)

Focus on NOUNS and ACTION VERBS, not generic modifiers.
Return just the keywords, one per line."""

    r1 = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": extract_prompt}],
        temperature=0
    )
    keywords = (r1.content[0].text or "").strip()
    log.info(f"  Extracted keywords: {keywords[:80]}...")

    # STAGE 2: Inject keywords while preserving meaning
    inject_prompt = f"""Inject these JD keywords into the bullet while preserving its meaning.

ORIGINAL BULLET:
{original_bullet}

KEYWORDS TO INCORPORATE:
{keywords}

RULES:
1. Keep the original meaning and facts exactly the same
2. Swap existing words with keyword synonyms where natural
3. Add brief keyword phrases ONLY if they clarify existing content
4. Do NOT add new claims, metrics, or achievements
5. Do NOT change the action or outcome described
6. Keep it natural - don't force keywords that don't fit
{char_text}
Return ONLY the keyword-optimized bullet. No explanation."""

    r2 = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": inject_prompt}],
        temperature=0.1
    )

    result = (r2.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def optimize_keywords_aggressive(original_bullet: str, job_description: str,
                                  stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Aggressive Keyword Optimization: Maximize keyword density.

    More liberal approach that:
    - Injects more JD terminology
    - May slightly restructure for keyword placement
    - Still preserves core meaning and facts
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_aggressive - '{original_bullet[:50]}...'")
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""

    prompt = f"""You are an ATS optimization expert. Maximize keyword alignment with the JD.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

YOUR TASK: Rewrite to maximize ATS keyword matching while preserving facts.

WHAT YOU CAN DO:
✓ Replace words with JD terminology (synonyms)
✓ Add brief qualifying phrases using JD keywords (e.g., "using data-driven approach")
✓ Reorder clauses to front-load important keywords
✓ Add domain context using JD terminology

WHAT YOU CANNOT DO:
✗ Add metrics, percentages, or numbers not in original
✗ Add tools or technologies not in original
✗ Change the core achievement or action
✗ Invent new responsibilities or outcomes
✗ Make vague claims specific

The bullet should still be factually identical to the original - just expressed
using the job description's vocabulary and terminology.
{char_text}
Return ONLY the optimized bullet. No explanation."""

    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    result = (r.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def optimize_keywords_with_context(original_bullet: str, job_description: str,
                                    stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Context-Aware Keyword Optimization: Uses stored facts to inform keyword choices.

    If facts are available, uses them to:
    - Select keywords that match actual skills/tools used
    - Add context that allows for more keyword incorporation
    - Still preserves factual accuracy
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    has_facts = bool(stored_facts and any(stored_facts.get(c) for c in
                     ["tools", "skills", "actions", "results", "situation", "timeline"]))

    log.info(f"optimize_keywords_with_context - '{original_bullet[:50]}...' (has_facts: {has_facts})")
    char_text = f"\nKeep under {char_limit} characters." if char_limit else ""

    if has_facts:
        facts_text = _format_facts(stored_facts)
        source_section = f"""ORIGINAL BULLET:
{original_bullet}

VERIFIED FACTS (can use for keyword context):
{facts_text}"""
    else:
        source_section = f"""ORIGINAL BULLET:
{original_bullet}

(No additional facts - only use information in the original bullet)"""

    prompt = f"""You are optimizing a resume bullet for ATS keyword matching.

{source_section}

JOB DESCRIPTION:
{job_description}

YOUR TASK: Inject JD keywords while preserving factual accuracy.

KEYWORD INJECTION STRATEGY:
1. Identify JD keywords that match the candidate's actual experience
2. Swap synonyms: Replace existing words with JD terminology
3. Add context: If facts support it, add brief phrases using JD keywords
4. Front-load: Put important keywords near the beginning

CONSTRAINTS:
- Every claim must be supported by original bullet OR verified facts
- Do NOT add metrics, tools, or skills not in the source material
- Keep the core meaning intact
- If no facts provided, work only with original bullet content
{char_text}
Return ONLY the keyword-optimized bullet. No explanation."""

    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    result = (r.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


def optimize_keywords_hybrid(original_bullet: str, job_description: str,
                              stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Hybrid Keyword Optimization: Generate + Select best keyword version.

    Multi-candidate approach for keywords:
    1. Generate 3 versions with different keyword strategies
    2. Score each for keyword alignment AND factual accuracy
    3. Return the best one
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"optimize_keywords_hybrid - '{original_bullet[:50]}...'")
    char_text = f"\nEach under {char_limit} chars." if char_limit else ""

    # STAGE 1: Generate 3 keyword-optimized versions
    gen_prompt = f"""Generate 3 versions of this bullet with different keyword optimization strategies.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

Create 3 versions:
VERSION 1 (Conservative): Only swap exact synonyms from JD
VERSION 2 (Moderate): Swap synonyms + add brief qualifying phrases with JD keywords
VERSION 3 (Aggressive): Maximize keyword density while preserving core facts

RULES FOR ALL VERSIONS:
- Keep the original achievement/action intact
- Do NOT add metrics, tools, or claims not in original
- Do NOT change the meaning
{char_text}

VERSION 1: [bullet]
VERSION 2: [bullet]
VERSION 3: [bullet]"""

    r1 = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": gen_prompt}],
        temperature=0.2
    )
    candidates = (r1.content[0].text or "").strip()
    log.info(f"  Generated 3 keyword versions")

    # STAGE 2: Select best version
    select_prompt = f"""Select the BEST keyword-optimized version.

ORIGINAL BULLET:
{original_bullet}

CANDIDATES:
{candidates}

EVALUATION CRITERIA (in order of importance):
1. FACTUAL ACCURACY - Does it preserve the original meaning exactly?
2. KEYWORD ALIGNMENT - How many relevant JD keywords are incorporated?
3. NATURAL FLOW - Does it read naturally, not keyword-stuffed?

Return ONLY the winning bullet text (no "VERSION X:")."""

    r2 = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": select_prompt}],
        temperature=0
    )

    selected = (r2.content[0].text or "").strip().lstrip("-• ")
    for prefix in ["VERSION 1:", "VERSION 2:", "VERSION 3:", "Winner:", "Best:"]:
        if selected.upper().startswith(prefix.upper()):
            selected = selected[len(prefix):].strip()

    log.info(f"  Selected: '{selected[:60]}...'")
    return selected


def generate_bullet_metrics_and_tools(original_bullet: str, job_description: str,
                                       stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Metrics & Tools Enhancement: ONLY add value when there's actual value to add.

    This is a highly conservative approach that only enhances bullets when:
    1. Stored facts contain QUANTITATIVE metrics (numbers, percentages, dollars)
    2. Stored facts contain TOOLS that are explicitly mentioned in the JD
    3. Stored facts contain SCOPE information (team size, timeline, budget)

    FORBIDDEN additions (even with facts):
    - Generic qualifiers: "strategic", "data-driven", "cross-functional", "evidence-based"
    - Vague intensifiers: "significantly", "substantially", "highly", "advanced"
    - Buzzwords: "leveraging", "utilizing", "driving insights", "synergy"
    - Assumptions beyond what facts explicitly state

    Philosophy: One real metric beats three buzzwords.

    Args:
        original_bullet: The original bullet text
        job_description: Target job description
        stored_facts: Structured facts with metrics, tools, actions, results
        char_limit: Optional character limit

    Returns:
        Enhanced bullet (or minimal keyword optimization if no metrics/tools to add)
    """
    if not client:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    log.info(f"generate_bullet_metrics_and_tools - '{original_bullet[:50]}...'")

    # Check if we have QUANTITATIVE enhancements to add
    has_metrics = False
    has_jd_tools = False
    has_scope = False

    if stored_facts:
        # Check for metrics in results
        results = stored_facts.get("results", [])
        if results:
            # Look for numbers, percentages, dollar amounts in results
            import re
            for result in results:
                if re.search(r'\d+[%$KMB]|\d+\+|\d{1,3}(,\d{3})*', str(result)):
                    has_metrics = True
                    break

        # Check for JD-relevant tools
        tools = stored_facts.get("tools", [])
        if tools:
            # Only count as "has tools" if JD mentions them
            for tool in tools:
                if tool.lower() in job_description.lower():
                    has_jd_tools = True
                    break

        # Check for scope information (team size, timeline, budget)
        situation = stored_facts.get("situation", "")
        timeline = stored_facts.get("timeline", "")
        if situation or timeline:
            # Look for team size, budget, duration indicators
            import re
            scope_indicators = r'\d+\s*(person|people|member|month|year|week|K|M|B|\$)'
            if re.search(scope_indicators, situation + timeline, re.IGNORECASE):
                has_scope = True

    meaningful_enhancements = has_metrics or has_jd_tools or has_scope

    log.info(f"  Enhancement check: metrics={has_metrics}, jd_tools={has_jd_tools}, scope={has_scope}")

    # If no meaningful enhancements, fall back to light keyword optimization
    if not meaningful_enhancements:
        log.info(f"  → No quantitative enhancements available, using light_touch keyword optimization")
        return optimize_keywords_light_touch(original_bullet, job_description, stored_facts, char_limit)

    # Build facts context showing ONLY the enhancement-worthy information
    facts_text = ""

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

    char_text = f"\nIMPORTANT: Keep the bullet under {char_limit} characters." if char_limit else ""

    log.info(f"  → Has quantitative enhancements, using metrics/tools optimization")

    prompt = f"""You are enhancing a resume bullet using VERIFIED FACTS. Be extremely conservative.

TARGET JOB DESCRIPTION:
{job_description}

ORIGINAL BULLET:
{original_bullet}

VERIFIED FACTS (your ONLY source material):
{facts_text}

YOUR TASK: Enhance this bullet ONLY by adding:
1. METRICS: Specific numbers, percentages, dollar amounts from the facts
2. TOOLS: Technologies/tools that BOTH (a) appear in facts AND (b) are mentioned in JD
3. SCOPE: Team size, timeline, or budget if it's in the facts

STRICT RULES - VIOLATIONS ARE UNACCEPTABLE:
✗ NO generic qualifiers: "strategic", "data-driven", "cross-functional", "evidence-based", "comprehensive"
✗ NO vague intensifiers: "significantly", "substantially", "highly", "advanced", "robust"
✗ NO buzzwords: "leveraging", "utilizing", "driving insights", "synergy", "best practices"
✗ NO tools unless BOTH in facts AND in JD (if facts say "Excel" but JD wants "Python", don't add "Python")
✗ NO assumptions (if facts say "used Python", don't say "advanced Python" or "Python scripting")
✗ NO rephrasing for the sake of it - only add if there's quantitative value

ACCEPTABLE ADDITIONS (examples):
✓ "$500M portfolio" if that number is in facts
✓ "20% improvement" if that metric is in facts
✓ "Python and SQL" if BOTH are in facts AND JD mentions them
✓ "6-person team" if team size is in facts
✓ "3-month timeline" if duration is in facts

PHILOSOPHY: A bullet with ONE real metric beats a bullet with three buzzwords.
If you can't add meaningful metrics/tools/scope, make minimal changes.

FORMAT: Use XYZ structure naturally (not formulaic):
- What was accomplished + measurable result (if in facts) + how it was done
- Examples: "Reduced costs 20% by automating...", "Led team of 8 to deliver...", "Analyzed $2.5B portfolio using SQL and Python..."

{char_text}
Return ONLY the enhanced bullet. No explanation."""

    response = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    enhanced = (response.content[0].text or "").strip().lstrip("-• ")

    log.info(f"  → Metrics/tools result: '{enhanced[:80]}...'")
    return enhanced


# =====================================================================
# ASYNC VERSIONS FOR PARALLEL PROCESSING
# =====================================================================

async def optimize_keywords_light_touch_async(original_bullet: str, job_description: str,
                                               stored_facts: Dict = None, char_limit: Optional[int] = None) -> str:
    """
    Async version of optimize_keywords_light_touch for parallel processing.

    Light Touch: Small adjustments allowed, but with explicit guardrails.
    Allows minor rephrasing beyond pure synonyms, but with a clear list of
    what is and isn't allowed.
    """
    if not async_client:
        raise RuntimeError("ANTHROPIC_API_KEY missing or async_client not initialized")

    log.info(f"optimize_keywords_light_touch_async - '{original_bullet[:50]}...'")
    char_text = f"Stay under {char_limit} characters." if char_limit else ""

    prompt = f"""Make small adjustments to align this bullet with the job description keywords.

ORIGINAL BULLET:
{original_bullet}

JOB DESCRIPTION:
{job_description}

ALLOWED (small adjustments):
✓ Swap synonyms (e.g., "built" → "developed")
✓ Reorder words slightly if meaning unchanged
✓ Use JD phrasing for concepts already present (e.g., if bullet says "talked to users" and JD says "user research", can say "conducted user research" IF the bullet already describes research activities)

FORBIDDEN (these invalidate the bullet):
✗ Adding tools/technologies not mentioned (SQL, Python, Tableau, etc.)
✗ Adding metrics or numbers not in original
✗ Adding audiences not mentioned (stakeholders, leadership, clients)
✗ Adding qualifiers that change scope (cross-functional, enterprise-wide, etc.)
✗ Adding deliverables not mentioned (frameworks, models, recommendations)
✗ Changing what was actually done

GOAL: A hiring manager reading both versions should believe they describe the exact same work.

{char_text}

Return ONLY the adjusted bullet, nothing else."""

    response = await async_client.messages.create(
        model=CHAT_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    result = (response.content[0].text or "").strip().lstrip("-• ")
    log.info(f"  Result: '{result[:60]}...'")
    return result


async def generate_bullet_metrics_and_tools_async(original_bullet: str, job_description: str,
                                                   stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Async version of generate_bullet_metrics_and_tools for parallel processing.

    Metrics & Tools Enhancement: ONLY add value when there's actual value to add.
    This function checks for quantitative enhancements and routes to the appropriate strategy.
    """
    if not async_client:
        raise RuntimeError("ANTHROPIC_API_KEY missing or async_client not initialized")

    log.info(f"generate_bullet_metrics_and_tools_async - '{original_bullet[:50]}...'")

    # Check if we have QUANTITATIVE enhancements to add
    has_metrics = False
    has_jd_tools = False
    has_scope = False

    if stored_facts:
        # Check for metrics in results
        results = stored_facts.get("results", [])
        if results:
            # Look for numbers, percentages, dollar amounts in results
            import re
            for result in results:
                if re.search(r'\d+[%$KMB]|\d+\+|\d{1,3}(,\d{3})*', str(result)):
                    has_metrics = True
                    break

        # Check for JD-relevant tools
        tools = stored_facts.get("tools", [])
        if tools:
            # Only count as "has tools" if JD mentions them
            for tool in tools:
                if tool.lower() in job_description.lower():
                    has_jd_tools = True
                    break

        # Check for scope information (team size, timeline, budget)
        situation = stored_facts.get("situation", "")
        timeline = stored_facts.get("timeline", "")
        if situation or timeline:
            # Look for team size, budget, duration indicators
            import re
            scope_indicators = r'\d+\s*(person|people|member|month|year|week|K|M|B|\$)'
            if re.search(scope_indicators, situation + timeline, re.IGNORECASE):
                has_scope = True

    meaningful_enhancements = has_metrics or has_jd_tools or has_scope

    log.info(f"  Enhancement check: metrics={has_metrics}, jd_tools={has_jd_tools}, scope={has_scope}")

    # If no meaningful enhancements, fall back to light keyword optimization
    if not meaningful_enhancements:
        log.info(f"  → No quantitative enhancements available, using light_touch keyword optimization")
        return await optimize_keywords_light_touch_async(original_bullet, job_description, stored_facts, char_limit)

    # Build facts context showing ONLY the enhancement-worthy information
    facts_text = ""

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

    char_text = f"\nIMPORTANT: Keep the bullet under {char_limit} characters." if char_limit else ""

    log.info(f"  → Has quantitative enhancements, using metrics/tools optimization")

    prompt = f"""You are enhancing a resume bullet using VERIFIED FACTS. Be extremely conservative.

TARGET JOB DESCRIPTION:
{job_description}

ORIGINAL BULLET:
{original_bullet}

VERIFIED FACTS (your ONLY source material):
{facts_text}

YOUR TASK: Enhance this bullet ONLY by adding:
1. METRICS: Specific numbers, percentages, dollar amounts from the facts
2. TOOLS: Technologies/tools that BOTH (a) appear in facts AND (b) are mentioned in JD
3. SCOPE: Team size, timeline, or budget if it's in the facts

STRICT RULES - VIOLATIONS ARE UNACCEPTABLE:
✗ NO generic qualifiers: "strategic", "data-driven", "cross-functional", "evidence-based", "comprehensive"
✗ NO vague intensifiers: "significantly", "substantially", "highly", "advanced", "robust"
✗ NO buzzwords: "leveraging", "utilizing", "driving insights", "synergy", "best practices"
✗ NO tools unless BOTH in facts AND in JD (if facts say "Excel" but JD wants "Python", don't add "Python")
✗ NO assumptions (if facts say "used Python", don't say "advanced Python" or "Python scripting")
✗ NO rephrasing for the sake of it - only add if there's quantitative value

ACCEPTABLE ADDITIONS (examples):
✓ "$500M portfolio" if that number is in facts
✓ "20% improvement" if that metric is in facts
✓ "Python and SQL" if BOTH are in facts AND JD mentions them
✓ "6-person team" if team size is in facts
✓ "3-month timeline" if duration is in facts

PHILOSOPHY: A bullet with ONE real metric beats a bullet with three buzzwords.
If you can't add meaningful metrics/tools/scope, make minimal changes.

FORMAT: Use XYZ structure naturally (not formulaic):
- What was accomplished + measurable result (if in facts) + how it was done
- Examples: "Reduced costs 20% by automating...", "Led team of 8 to deliver...", "Analyzed $2.5B portfolio using SQL and Python..."

{char_text}
Return ONLY the enhanced bullet. No explanation."""

    response = await async_client.messages.create(
        model=CHAT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    enhanced = (response.content[0].text or "").strip().lstrip("-• ")

    log.info(f"  → Metrics/tools result: '{enhanced[:80]}...'")
    return enhanced

