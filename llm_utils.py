import re, hashlib
from json import loads
from typing import List, Dict
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