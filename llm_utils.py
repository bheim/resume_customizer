import re, hashlib
from json import loads
from typing import List, Dict, Optional, Tuple
from config import client, CHAT_MODEL, EMBED_MODEL, USE_DISTILLED_JD, USE_LLM_TERMS, log
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
    r = client.chat.completions.create(model=CHAT_MODEL, messages=[{"role":"user","content":prompt}], temperature=0)
    distilled = (r.choices[0].message.content or "").strip()
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
    r = client.chat.completions.create(model=CHAT_MODEL, messages=[{"role":"user","content":prompt}], temperature=0)
    raw = (r.choices[0].message.content or "").strip()
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
    if not client: return []
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
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
    r = client.chat.completions.create(model=CHAT_MODEL, messages=[{"role":"user","content":prompt}], temperature=0)
    out = (r.choices[0].message.content or "").strip()
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
        r = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0  # Deterministic for consistent grading
        )

        raw = (r.choices[0].message.content or "").strip()

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

def rewrite_with_openai(bullets: List[str], job_description: str) -> List[str]:
    if not client: raise RuntimeError("OPENAI_API_KEY missing")
    jd_core = llm_distill_jd(job_description) if USE_DISTILLED_JD else job_description
    if USE_LLM_TERMS:
        jd_terms_struct = llm_extract_terms(jd_core)
        SOFT = re.compile(r"\b(communication|teamwork|collaboration|interpersonal|self[- ]starter|detail[- ]oriented)\b", re.I)
        terms_flat = []
        for cat in ["tools","responsibilities","domains","certifications","seniority","skills"]:
            for t in jd_terms_struct.get(cat, []):
                if SOFT.search(t): continue
                terms_flat.append(t)
    else:
        terms_flat = [t for t in top_terms(jd_core, k=25) if not re.search(r"\b(communication|teamwork|collaboration)\b", t, re.I)]
    terms_line = ", ".join(terms_flat[:40]); n = len(bullets)
    prompt = (
        f"You will rewrite {n} resume bullets based on the provided job description.\n"
        "- Outcome → metric → tool/domain. Concise. Same person/tense.\n"
        f"- Return STRICT JSON: an array of {n} strings. No prose. No code fences.\n\n"
        "ROLE CORE:\n" + jd_core + "\n\n"
        "ROLE-CRITICAL TERMS:\n" + terms_line + "\n\n"
        "INPUT_BULLETS:\n" + "\n".join([f"{i+1}. {b}" for i, b in enumerate(bullets)]) + "\n\nReturn JSON ONLY like: [\"...\", \"...\"]"
    )
    r = client.chat.completions.create(model=CHAT_MODEL, messages=[{"role":"user","content":prompt}], temperature=0)
    raw = (r.choices[0].message.content or "").strip()
    def _parse_json_list(s: str) -> List[str]:
        s2 = s.strip()
        if s2.startswith("```"):
            s2 = s2.strip("`")
            s2 = re.sub(r"^\s*json", "", s2, flags=re.I).strip()
        lst = loads(s2)
        if not isinstance(lst, list): raise ValueError("not a list")
        return [str(x).replace("\n", " ").strip().lstrip("-• ").strip() for x in lst]
    try:
        lines = _parse_json_list(raw)
    except Exception:
        r2 = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role":"user","content":f"Your prior output was not valid JSON. Return ONLY a JSON array of {n} strings. No commentary. No code fences."}],
            temperature=0
        )
        lines = _parse_json_list((r2.choices[0].message.content or "").strip())
    if len(lines) != n:
        log.warning(f"LLM count mismatch: got={len(lines)} expected={n}. Applying pad/trim fallback.")
        lines = (lines + bullets[len(lines):])[:n]
    log.info(f"OpenAI response lines: {len(lines)}")
    return lines


def generate_followup_questions(bullets: List[str], job_description: str,
                                existing_context: Optional[List[Dict[str, str]]] = None,
                                max_questions: int = 10) -> List[Dict[str, str]]:
    """
    Generate follow-up questions to gather more context about the user's experience.
    Each question is associated with a specific bullet point.

    Args:
        bullets: List of resume bullet points
        job_description: The target job description
        existing_context: Previously answered Q&A pairs to avoid repeating
        max_questions: Maximum number of questions to generate (default 10, but LLM decides actual count)

    Returns:
        List of dicts with 'question', 'type', 'bullet_index', and 'bullet_text' keys
    """
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Build context string from existing Q&A
    context_str = ""
    if existing_context:
        context_str = "\n\nPREVIOUSLY ANSWERED QUESTIONS (DO NOT ask similar or duplicate questions):\n"
        for qa in existing_context:
            context_str += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
        context_str += "IMPORTANT: Do NOT generate questions that are similar to or overlap with the questions above. The user has already provided this information.\n"

    bullets_text = "\n".join([f"{i+1}. {b}" for i, b in enumerate(bullets)])

    prompt = f"""You are a career counselor helping someone tailor their resume. For each resume bullet below, determine if you need to ask follow-up questions to write stronger bullets.

IMPORTANT: Be conservative - only ask questions if there are CLEAR gaps (missing metrics, unclear impact, vague technologies). If a bullet is already strong, don't ask about it.

Focus on:
1. Quantifiable metrics and achievements they may have omitted
2. Specific technologies, tools, or methodologies relevant to the target role
3. Impact and outcomes of their work
4. Team size, scope, or scale of their responsibilities
5. Specific challenges they overcame

TARGET JOB DESCRIPTION:
{job_description}

CURRENT RESUME BULLETS:
{bullets_text}
{context_str}
For each bullet that needs clarification, generate a question. Associate each question with the bullet number it's about.

Return ONLY valid JSON in this format (with as many or as few questions as needed, up to {max_questions}):
[
  {{"question": "...", "type": "metrics", "bullet_index": 0}},
  {{"question": "...", "type": "technical", "bullet_index": 1}},
  {{"question": "...", "type": "impact", "bullet_index": 0}}
]

Valid types: metrics, technical, impact, scope, challenges, achievements
bullet_index is the 0-based index of the bullet (0 for first bullet, 1 for second, etc.)"""

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    raw = (r.choices[0].message.content or "").strip()

    # Parse JSON response
    try:
        questions = _parse_json_questions(raw)
        # Add bullet_text to each question
        for q in questions:
            bullet_idx = q.get("bullet_index", 0)
            if 0 <= bullet_idx < len(bullets):
                q["bullet_text"] = bullets[bullet_idx]
            else:
                q["bullet_text"] = bullets[0] if bullets else ""
    except Exception as e:
        log.exception(f"Failed to parse questions JSON: {e}")
        # Fallback questions
        questions = [
            {"question": "What quantifiable metrics or results did you achieve in these roles?", "type": "metrics", "bullet_index": 0, "bullet_text": bullets[0] if bullets else ""},
            {"question": "What specific technologies or tools relevant to this job did you use?", "type": "technical", "bullet_index": 0, "bullet_text": bullets[0] if bullets else ""},
            {"question": "What was the business impact of your work?", "type": "impact", "bullet_index": 0, "bullet_text": bullets[0] if bullets else ""}
        ]

    return questions[:max_questions]


def _parse_json_questions(s: str) -> List[Dict[str, str]]:
    """Parse JSON questions response from LLM."""
    s2 = s.strip()
    if s2.startswith("```"):
        s2 = s2.strip("`")
        s2 = re.sub(r"^\s*json", "", s2, flags=re.I).strip()

    data = loads(s2)
    if not isinstance(data, list):
        raise ValueError("Expected a list of questions")

    return [{"question": q.get("question", ""), "type": q.get("type", "general"), "bullet_index": q.get("bullet_index", 0)}
            for q in data if isinstance(q, dict) and "question" in q]


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
        return False, "OpenAI client not available"

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

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    response = (r.choices[0].message.content or "").strip()

    # Parse response
    if response.startswith("YES"):
        reason = response.split("|", 1)[1] if "|" in response else "Sufficient context"
        return False, reason
    else:
        reason = response.split("|", 1)[1] if "|" in response else "Need more context"
        return True, reason


def rewrite_with_context(bullets: List[str], job_description: str,
                        qa_context: List[Dict[str, str]]) -> List[str]:
    """
    Rewrite resume bullets using both job description and Q&A context.
    Uses Google XYZ format and custom prompting strategy.

    Args:
        bullets: Original resume bullets
        job_description: Target job description
        qa_context: List of Q&A pairs with additional context

    Returns:
        List of rewritten bullets
    """
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Build Contextual Q&A section
    qa_section = ""
    if qa_context:
        qa_section = "\n⸻\nContextual Q&A (verbatim):\n"
        for qa in qa_context:
            qa_section += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
        qa_section += "⸻\n"

    # Build current bullets section
    bullets_section = "Current Bullets:\n" + "\n".join([f"• {b}" for b in bullets])

    n = len(bullets)

    prompt = f"""You are continuing as the same expert resume coach.
You already have the user's context from earlier answers (quantitative results, methods, frameworks, outcomes, team size, tools used, etc.).
Use the section titled "Contextual Q&A (verbatim)" as authoritative facts; do not ask new questions.

Goal: Customize the same bullets for a new job description.
• Use all provided context automatically (both base bullets and Q&A).
• Do not ask follow-up questions; produce final bullets immediately.

Standing Principles for All Roles
• Preserve ownership and initiative language even if the JD uses low-agency verbs (e.g., "support," "assist," "collaborate").
• Translate competencies, do not mirror phrasing.
• Prioritize impact, metrics, and decision-making authority over surface similarity to JD wording.
• Always output in the Google XYZ structure: Accomplished [X] as measured by [Y] by doing [Z].
• If teamwork is emphasized, frame as leadership within collaboration (e.g., "led cross-functional…").

Rewriting Guidelines:
• Use the Google XYZ formula: Accomplished [X] as measured by [Y] by doing [Z].
• Keep bullets concise (≤ 25 words ideally).
• Maintain strong action verbs and alignment with the new JD's competencies.
• Return bullets as a simple numbered list, no commentary.
• Return STRICT JSON: an array of exactly {n} strings. No prose. No code fences.

⸻
New Job Description:
{job_description}
{qa_section}
{bullets_section}
⸻
Return ONLY a JSON array of {n} rewritten bullets like: ["...", "..."]"""

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    raw = (r.choices[0].message.content or "").strip()

    def _parse_json_list(s: str) -> List[str]:
        s2 = s.strip()
        if s2.startswith("```"):
            s2 = s2.strip("`")
            s2 = re.sub(r"^\s*json", "", s2, flags=re.I).strip()
        lst = loads(s2)
        if not isinstance(lst, list):
            raise ValueError("not a list")
        return [str(x).replace("\n", " ").strip().lstrip("-• ").strip() for x in lst]

    try:
        lines = _parse_json_list(raw)
    except Exception:
        r2 = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": f"Your prior output was not valid JSON. Return ONLY a JSON array of {n} strings. No commentary. No code fences."}],
            temperature=0
        )
        lines = _parse_json_list((r2.choices[0].message.content or "").strip())

    if len(lines) != n:
        log.warning(f"LLM count mismatch: got={len(lines)} expected={n}. Applying pad/trim fallback.")
        lines = (lines + bullets[len(lines):])[:n]

    log.info(f"OpenAI response lines with context: {len(lines)}")
    return lines


def extract_facts_from_qa(bullet_text: str, qa_pairs: List[Dict[str, str]]) -> Dict:
    """
    Extract structured facts from Q&A conversation for a single bullet.

    This function converts raw Q&A pairs into a structured format that can be:
    1. Shown to the user for confirmation/editing
    2. Stored in the database for future use
    3. Used to generate tailored bullets without re-asking questions

    Args:
        bullet_text: The original bullet text
        qa_pairs: List of {"question": str, "answer": str} dictionaries

    Returns:
        Structured facts following BulletFacts schema:
        {
            "metrics": {
                "quantifiable_achievements": [...],
                "scale": [...]
            },
            "technical_details": {
                "technologies": [...],
                "methodologies": [...]
            },
            "impact": {
                "business_outcomes": [...],
                "stakeholder_value": [...]
            },
            "context": {
                "challenges_solved": [...],
                "scope": [...],
                "role": [...]
            },
            "raw_qa": [...]  # Original Q&A preserved
        }
    """
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Build Q&A text
    qa_text = ""
    for qa in qa_pairs:
        qa_text += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"

    prompt = f"""You are extracting structured facts from a Q&A conversation about a resume bullet.

ORIGINAL BULLET:
{bullet_text}

Q&A CONVERSATION:
{qa_text}

Extract and organize the facts from this conversation into structured categories. Be comprehensive but accurate - only include information that was explicitly stated in the answers.

Return STRICT JSON with this exact structure:

{{
  "metrics": {{
    "quantifiable_achievements": ["Achievement with number/percentage", "Another metric"],
    "scale": ["Team size", "Volume/scale numbers", "Timeline/duration"]
  }},
  "technical_details": {{
    "technologies": ["Specific tools", "Languages", "Frameworks", "Platforms"],
    "methodologies": ["Agile", "CI/CD", "Specific processes"]
  }},
  "impact": {{
    "business_outcomes": ["Revenue impact", "Efficiency gains", "User metrics"],
    "stakeholder_value": ["How it helped specific teams/users", "Business value"]
  }},
  "context": {{
    "challenges_solved": ["Specific problems addressed"],
    "scope": ["Project timeline", "Team structure", "Organizational scope"],
    "role": ["Specific contributions", "Leadership aspects", "Responsibilities"]
  }}
}}

IMPORTANT:
- Only include facts that are clearly stated in the answers
- Use exact numbers/percentages when provided
- Keep each item concise (1-2 sentences max)
- If a category has no information, use an empty array
- Do NOT include the raw Q&A in this structure (that will be added separately)
- Return ONLY valid JSON, no commentary or code fences"""

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    raw = (r.choices[0].message.content or "").strip()

    # Parse JSON response
    try:
        # Clean potential code fences
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = re.sub(r"^\s*json", "", raw, flags=re.I).strip()

        facts = loads(raw)

        # Validate structure
        expected_keys = {
            "metrics": ["quantifiable_achievements", "scale"],
            "technical_details": ["technologies", "methodologies"],
            "impact": ["business_outcomes", "stakeholder_value"],
            "context": ["challenges_solved", "scope", "role"]
        }

        for category, subkeys in expected_keys.items():
            if category not in facts:
                facts[category] = {}
            for subkey in subkeys:
                if subkey not in facts[category]:
                    facts[category][subkey] = []

        # Add raw Q&A for reference
        facts["raw_qa"] = qa_pairs

        log.info(f"Extracted facts for bullet: {len(qa_pairs)} Q&A pairs")
        return facts

    except Exception as e:
        log.exception(f"Failed to parse facts JSON: {e}")
        # Return minimal structure with raw Q&A
        return {
            "metrics": {"quantifiable_achievements": [], "scale": []},
            "technical_details": {"technologies": [], "methodologies": []},
            "impact": {"business_outcomes": [], "stakeholder_value": []},
            "context": {"challenges_solved": [], "scope": [], "role": []},
            "raw_qa": qa_pairs
        }


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
        log.debug(f"  Calling OpenAI with temperature=0.3")
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3  # Slightly higher for variety, still controlled
        )
        enhanced = response.choices[0].message.content.strip()

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
        raise RuntimeError("OPENAI_API_KEY missing")

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

    prompt = f"""You are a professional resume writer. Rewrite this bullet using the provided facts and tailoring it to the job description.

ORIGINAL BULLET:
{original_bullet}

TARGET JOB DESCRIPTION:
{job_description}

VERIFIED FACTS ABOUT THIS EXPERIENCE:
{facts_text}

REWRITING GUIDELINES:
• Use impact-driven formats inspired by Google XYZ (but vary the structure for uniqueness):
  Examples:
  - "[Action] [X] resulting in [Y]"
  - "[Action] [X], achieving [Y]"
  - "[Action] [X] by doing [Z]"
  - "[Action] [X] to drive [Y]"
  - "[Action] [X], improving [Y] by [Z]"
  - "[Action] [X] through [Z], delivering [Y]"

  AVOID using "as measured by" in every bullet - use natural language variations

• Start with strong, impactful action verbs that match the job description
  Examples: Led, Developed, Engineered, Optimized, Architected, Drove, Delivered, Built, Designed, Implemented, Spearheaded
  (Choose the verb that best fits the accomplishment AND aligns with JD language)

• Incorporate specific metrics and achievements from the facts
• Align with the job description's requirements and terminology
• Preserve ownership language and demonstrate impact
• Keep it concise, powerful, and unique
• Use variety in structure - don't make all bullets sound the same
• DO NOT add information not present in the facts{char_limit_text}

Return ONLY the rewritten bullet, no commentary or explanation."""

    # Log the full prompt so it's visible in logs
    log.info(f"  ===== WITH-FACTS PROMPT START =====")
    log.info(prompt)
    log.info(f"  ===== WITH-FACTS PROMPT END =====")

    log.debug(f"  Calling OpenAI with temperature=0.4 for variety")
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4  # Higher for structural variety while staying factual
    )

    enhanced_bullet = (r.choices[0].message.content or "").strip()

    # Clean up any bullet markers or extra formatting
    enhanced_bullet = enhanced_bullet.lstrip("-• ").strip()

    log.info(f"  → With-facts result: '{enhanced_bullet[:80]}...'")
    log.info(f"  → Generated bullet: {len(enhanced_bullet)} chars")
    log.debug(f"  Full bullet: '{enhanced_bullet}'")

    return enhanced_bullet


def generate_bullets_with_facts(bullets: List[str], job_description: str,
                                bullet_facts_map: Dict[int, Dict]) -> List[str]:
    """
    Generate enhanced bullets for multiple bullets using stored facts.

    Args:
        bullets: List of original bullets
        job_description: Target job description
        bullet_facts_map: Dictionary mapping bullet index to stored facts
                         {0: facts_dict, 1: facts_dict, ...}

    Returns:
        List of enhanced bullets (same length as input)
    """
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    enhanced_bullets = []

    for idx, bullet in enumerate(bullets):
        if idx in bullet_facts_map and bullet_facts_map[idx]:
            # Use facts-based generation
            log.info(f"Generating bullet {idx+1} with stored facts")
            enhanced = generate_bullet_with_facts(bullet, job_description, bullet_facts_map[idx])
            enhanced_bullets.append(enhanced)
        else:
            # Fallback to basic rewriting (no facts available)
            log.info(f"Generating bullet {idx+1} without facts (fallback to basic rewrite)")
            # Use single-bullet rewrite (we'll create a simple version)
            enhanced_bullets.append(bullet)  # Placeholder - can improve with basic rewrite logic

    return enhanced_bullets

# =====================================================================
# NEW CONVERSATIONAL & IMPROVED PROMPTS
# =====================================================================

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
        raise RuntimeError("OPENAI_API_KEY missing")

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

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )

    question = (r.choices[0].message.content or "").strip()
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
        raise RuntimeError("OPENAI_API_KEY missing")

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

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0
    )

    raw = (r.choices[0].message.content or "").strip()

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


def extract_jd_keywords(job_description: str) -> Dict:
    """
    Extract the most important keywords, skills, and requirements from a job description.

    Args:
        job_description: The full job description text

    Returns:
        Dictionary with required_skills, nice_to_have_skills, key_responsibilities,
        experience_level, and industry_context
    """
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Check cache
    h = "keywords:" + jd_hash(job_description)
    if h in _terms_cache:
        return _terms_cache[h]

    system_prompt = """Extract the most important keywords, skills, and requirements from this job description.

Focus on:
- Required skills and technologies
- Key responsibilities
- Desired experience/qualifications
- Important industry terms or methodologies

Output as JSON:
{
  "required_skills": ["skill 1", "skill 2"],
  "nice_to_have_skills": ["skill 3", "skill 4"],
  "key_responsibilities": ["resp 1", "resp 2"],
  "experience_level": "description",
  "industry_context": "relevant industry/domain info"
}"""

    user_prompt = f"""Job Description:
{job_description}

Extract key requirements and keywords."""

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0
    )

    raw = (r.choices[0].message.content or "").strip()

    try:
        # Clean potential code fences
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = re.sub(r"^\s*json", "", raw, flags=re.I).strip()

        keywords = loads(raw)

        # Ensure all expected keys exist
        default_structure = {
            "required_skills": [],
            "nice_to_have_skills": [],
            "key_responsibilities": [],
            "experience_level": "",
            "industry_context": ""
        }

        for key, default_value in default_structure.items():
            if key not in keywords:
                keywords[key] = default_value

        # Cache the result
        _terms_cache[h] = keywords

        log.info(f"Extracted keywords from JD: {len(keywords['required_skills'])} required skills")
        return keywords

    except Exception as e:
        log.exception(f"Failed to parse JD keywords: {e}")
        # Return minimal structure
        return {
            "required_skills": [],
            "nice_to_have_skills": [],
            "key_responsibilities": [],
            "experience_level": "",
            "industry_context": ""
        }


def generate_bullet_with_keywords(
    original_bullet: str,
    extracted_facts: Dict,
    jd_keywords: Dict,
    char_limit: Optional[int] = 150
) -> str:
    """
    Generate an enhanced bullet using the XYZ format with JD keywords.

    Uses the improved prompt that emphasizes:
    - XYZ format: "Accomplished [X] as measured by [Y] by doing [Z]"
    - Strong action verbs
    - Specific metrics from facts
    - Keywords from JD naturally integrated
    - Under character limit

    Args:
        original_bullet: The original bullet text
        extracted_facts: Facts extracted from conversation (situation, actions, results, skills, tools)
        jd_keywords: Keywords extracted from job description
        char_limit: Maximum character length (default 150)

    Returns:
        Enhanced bullet string
    """
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Build facts summary
    situation = extracted_facts.get("situation", "")
    actions = extracted_facts.get("actions", [])
    results = extracted_facts.get("results", [])
    skills = extracted_facts.get("skills", [])
    tools = extracted_facts.get("tools", [])

    actions_list = "\n".join([f"- {a}" for a in actions]) if actions else "Not specified"
    results_list = "\n".join([f"- {r}" for r in results]) if results else "Not specified"
    skills_list = ", ".join(skills) if skills else "Not specified"
    tools_list = ", ".join(tools) if tools else "Not specified"

    # Build JD requirements summary
    required_skills = ", ".join(jd_keywords.get("required_skills", []))
    key_responsibilities = "\n".join([f"- {r}" for r in jd_keywords.get("key_responsibilities", [])])

    system_prompt = """You are a professional resume writer. Generate a compelling resume bullet that:

1. Uses the XYZ format: "Accomplished [X] as measured by [Y] by doing [Z]"
2. Starts with a strong action verb (Led, Developed, Drove, Implemented, etc.)
3. Includes specific metrics when available
4. Emphasizes keywords from the job description naturally
5. Is 1-2 lines maximum (under 150 characters ideal)
6. Uses active voice and professional tone

CRITICAL RULES:
- Only use facts provided - never invent metrics or details
- If no metrics available, focus on scope and methods
- Emphasize the most relevant aspects for this specific job
- Be specific and concrete, avoid generic statements"""

    char_limit_text = f"\n\nIMPORTANT: Keep under {char_limit} characters." if char_limit else ""

    user_prompt = f"""Target Job Requirements:
{required_skills}

Key Responsibilities:
{key_responsibilities}

Original Bullet: "{original_bullet}"

Available Facts:
Situation: {situation}

Actions:
{actions_list}

Results:
{results_list}

Skills: {skills_list}
Tools: {tools_list}

Generate ONE enhanced bullet that emphasizes the most relevant aspects for this job description.{char_limit_text}"""

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0
    )

    enhanced_bullet = (r.choices[0].message.content or "").strip()

    # Clean up any bullet markers or extra formatting
    enhanced_bullet = enhanced_bullet.lstrip("-• ").strip()

    # Enforce character limit if needed
    if char_limit and len(enhanced_bullet) > char_limit:
        log.warning(f"Bullet exceeds {char_limit} chars: {len(enhanced_bullet)}")
        # Truncate at last complete word before limit
        truncated = enhanced_bullet[:char_limit].rsplit(' ', 1)[0] + "..."
        enhanced_bullet = truncated

    log.info(f"Generated enhanced bullet: {len(enhanced_bullet)} chars")
    return enhanced_bullet
