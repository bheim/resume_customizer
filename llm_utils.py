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


def generate_bullet_with_facts(original_bullet: str, job_description: str,
                               stored_facts: Dict, char_limit: Optional[int] = None) -> str:
    """
    Generate enhanced bullet using stored facts instead of raw Q&A.

    This is the optimized generation flow that uses pre-extracted, user-confirmed facts.

    Args:
        original_bullet: The original bullet text
        job_description: Target job description
        stored_facts: Structured facts from extract_facts_from_qa()
        char_limit: Optional character limit for the bullet

    Returns:
        Enhanced bullet string
    """
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Build facts context
    facts_text = ""

    # Metrics
    if stored_facts.get("metrics"):
        metrics = stored_facts["metrics"]
        if metrics.get("quantifiable_achievements"):
            facts_text += "Quantifiable Achievements:\n"
            for item in metrics["quantifiable_achievements"]:
                facts_text += f"• {item}\n"
        if metrics.get("scale"):
            facts_text += "Scale/Scope:\n"
            for item in metrics["scale"]:
                facts_text += f"• {item}\n"

    # Technical details
    if stored_facts.get("technical_details"):
        tech = stored_facts["technical_details"]
        if tech.get("technologies"):
            facts_text += f"Technologies: {', '.join(tech['technologies'])}\n"
        if tech.get("methodologies"):
            facts_text += f"Methodologies: {', '.join(tech['methodologies'])}\n"

    # Impact
    if stored_facts.get("impact"):
        impact = stored_facts["impact"]
        if impact.get("business_outcomes"):
            facts_text += "Business Impact:\n"
            for item in impact["business_outcomes"]:
                facts_text += f"• {item}\n"
        if impact.get("stakeholder_value"):
            facts_text += "Stakeholder Value:\n"
            for item in impact["stakeholder_value"]:
                facts_text += f"• {item}\n"

    # Context
    if stored_facts.get("context"):
        context = stored_facts["context"]
        if context.get("challenges_solved"):
            facts_text += "Challenges Solved:\n"
            for item in context["challenges_solved"]:
                facts_text += f"• {item}\n"
        if context.get("scope"):
            facts_text += "Project Scope:\n"
            for item in context["scope"]:
                facts_text += f"• {item}\n"
        if context.get("role"):
            facts_text += "Your Role:\n"
            for item in context["role"]:
                facts_text += f"• {item}\n"

    char_limit_text = f"\nIMPORTANT: Keep the bullet under {char_limit} characters." if char_limit else ""

    prompt = f"""You are a professional resume writer. Rewrite this bullet using the provided facts and tailoring it to the job description.

ORIGINAL BULLET:
{original_bullet}

TARGET JOB DESCRIPTION:
{job_description}

VERIFIED FACTS ABOUT THIS EXPERIENCE:
{facts_text}

REWRITING GUIDELINES:
• Use the Google XYZ formula: Accomplished [X] as measured by [Y] by doing [Z]
• Incorporate specific metrics and achievements from the facts
• Align with the job description's requirements and terminology
• Preserve ownership language and demonstrate impact
• Keep it concise and powerful
• DO NOT add information not present in the facts{char_limit_text}

Return ONLY the rewritten bullet, no commentary or explanation."""

    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    enhanced_bullet = (r.choices[0].message.content or "").strip()

    # Clean up any bullet markers or extra formatting
    enhanced_bullet = enhanced_bullet.lstrip("-• ").strip()

    log.info(f"Generated bullet with facts: {len(enhanced_bullet)} chars")
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