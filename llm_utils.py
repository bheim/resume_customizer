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
4. Is it concise?

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

