import os
import sys
import logging
import hashlib
import base64
from io import BytesIO
from copy import deepcopy
from typing import List, Tuple, Optional, Dict
from math import ceil
import re
from collections import Counter
from json import loads

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from openai import OpenAI
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.enum.section import WD_SECTION_START

# -------------------- Logging --------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("resume")
log.propagate = True

# -------------------- OpenAI --------------------
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

# -------------------- Feature toggles --------------------
USE_LLM_TERMS = os.getenv("USE_LLM_TERMS", "1") == "1"
USE_DISTILLED_JD = os.getenv("USE_DISTILLED_JD", "1") == "1"
W_DISTILLED = float(os.getenv("W_DISTILLED", "0.7"))  # weight for distilled JD in semantic sim

# -------------------- Caps and retries --------------------
REPROMPT_TRIES = int(os.getenv("REPROMPT_TRIES", "3"))

# -------------------- Scoring weights --------------------
W_EMB = float(os.getenv("W_EMB", "0.4"))
W_KEY = float(os.getenv("W_KEY", "0.2"))
W_LLM = float(os.getenv("W_LLM", "0.4"))

# -------------------- FastAPI --------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# -------------------- Health --------------------
@app.get("/")
def root():
    return {
        "status": "ok",
        "openai": bool(OPENAI_KEY),
        "models": {"embed": EMBED_MODEL, "chat": CHAT_MODEL},
        "weights": {"emb": W_EMB, "keywords": W_KEY, "llm": W_LLM, "semantic_distilled_weight": W_DISTILLED},
        "features": {"use_llm_terms": USE_LLM_TERMS, "use_distilled_jd": USE_DISTILLED_JD},
        "reprompt_tries": REPROMPT_TRIES,
    }

# -------------------- DOCX helpers --------------------
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

def _collect_links(p):
    links, p_el = [], p._p
    for h in p_el.findall(f".//{{{W_NS}}}hyperlink"):
        r_texts, rPr_template = [], None
        for r in h.findall(f".//{{{W_NS}}}r"):
            t = r.find(f".//{{{W_NS}}}t")
            if t is not None and t.text:
                r_texts.append(t.text)
            rPr = r.find(f"./{{{W_NS}}}rPr")
            if rPr is not None and rPr_template is None:
                rPr_template = deepcopy(rPr)
        anchor_text = "".join(r_texts).strip()
        r_id = h.get(qn("r:id")); url = None
        if r_id:
            try:
                rel = p.part.rels[r_id]
                if rel.is_external and rel.reltype == RT.HYPERLINK:
                    url = rel.target_ref
            except KeyError:
                pass
        if anchor_text and url:
            links.append({"text": anchor_text, "url": url, "rPr": rPr_template})
    return links

def _make_run(text, rPr_template=None):
    r = OxmlElement("w:r")
    if rPr_template is not None:
        r.append(deepcopy(rPr_template))
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r

def _make_hyperlink_run(p, text, url, rPr_template=None):
    r_id = p.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), r_id)
    h.append(_make_run(text, rPr_template))
    return h

def set_paragraph_text_with_selective_links(p, new_text):
    p_el = p._p
    tmpl = None
    for r in p_el.findall(f"./{{{W_NS}}}r"):
        tmpl = r.find(f"./{{{W_NS}}}rPr")
        if tmpl is not None:
            tmpl = deepcopy(tmpl)
        break
    links = _collect_links(p)
    anchors = sorted(links, key=lambda d: len(d["text"]), reverse=True)
    lower = new_text.lower(); spans=[]; i=0
    while i < len(new_text):
        match=None
        for lk in anchors:
            a=lk["text"]; al=a.lower()
            if lower.startswith(al, i):
                match=(i, i+len(a), lk); break
        if match:
            spans.append(match); i=match[1]
        else:
            next_pos=len(new_text)
            for lk in anchors:
                j=lower.find(lk["text"].lower(), i)
                if j!=-1: next_pos=min(next_pos, j)
            spans.append((i, next_pos, None)); i=next_pos
    for child in list(p_el):
        if child.tag != f"{{{W_NS}}}pPr":
            p_el.remove(child)
    for start,end,lk in spans:
        seg=new_text[start:end]
        if not seg: continue
        p_el.append(_make_hyperlink_run(p, seg, lk["url"], lk["rPr"] or tmpl) if lk else _make_run(seg, tmpl))

def enforce_single_page(doc: Document):
    body = doc.element.body
    for p in doc.paragraphs:
        for br in list(p._element.findall(f".//{{{W_NS}}}br")):
            if br.get(qn("w:type")) == "page":
                br.getparent().remove(br)
        pPr = p._p.pPr
        if pPr is not None:
            for pb in list(pPr.findall(f"./{{{W_NS}}}pageBreakBefore")):
                pPr.remove(pb)
    for sectPr in body.findall(f".//{{{W_NS}}}sectPr"):
        t = sectPr.find(f"./{{{W_NS}}}type") or OxmlElement("w:type")
        t.set(qn("w:val"), "continuous")
        if t.getparent() is None:
            sectPr.append(t)
    try:
        if doc.sections:
            doc.sections[-1].start_type = WD_SECTION_START.CONTINUOUS
    except Exception:
        pass
    def _body_p(): return body.findall(f"./{{{W_NS}}}p")
    while len(_body_p())>1 and not doc.paragraphs[-1].text.strip():
        body.remove(doc.paragraphs[-1]._element)

# -------------------- Bullet discovery --------------------
def collect_word_numbered_bullets(doc: Document) -> Tuple[List[str], List]:
    bullets, paras = [], []
    for p in doc.paragraphs:
        pPr = p._p.pPr
        if not (
            (pPr is not None)
            and (getattr(pPr, "numPr", None) is not None)
            and (getattr(pPr.numPr, "numId", None) is not None)
            and (getattr(pPr.numPr.numId, "val", None) is not None)
        ):
            continue
        text = p.text.strip()
        if text:
            bullets.append(text)
            paras.append(p)
    return bullets, paras

# -------------------- Tiered caps --------------------
def tiered_char_cap(orig_len: int, override: Optional[int] = None) -> int:
    if override and override > 0:
        return override
    if orig_len <= 110:
        return 100
    if orig_len <= 210:
        return 200
    return 300

def enforce_char_cap_with_reprompt(cur: str, cap: int) -> str:
    text = (cur or "").strip().lstrip("-• ").strip()
    if not client:
        return text[:cap].rstrip()
    if len(text) <= cap:
        return text
    for t in range(REPROMPT_TRIES):
        prompt = (
            f"Rewrite this resume bullet in {cap} characters or fewer. "
            "Preserve numbers and the core result. Use one concise clause. No filler. "
            "Return only the bullet text, no dash, no quotes.\n\n"
            f"Bullet:\n{text}"
        )
        r = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        nxt = r.choices[0].message.content.strip().lstrip("-• ").strip()
        log.info(f"reprompt try={t+1} cap={cap} prev_len={len(text)} new_len={len(nxt)}")
        text = nxt
        if len(text) <= cap:
            break
    if len(text) > cap:
        log.info(f"truncate len={len(text)} -> cap={cap}")
        text = text[:cap].rstrip()
    return text

# -------------------- Keyword + scoring utilities --------------------
STOPWORDS = set("""
a an the and or for of to in on at by with from as is are was were be been being
this that these those such into across over under within without not no nor than
your you we they he she it their our us
""".split())
TOKEN_RE = re.compile(r"[A-Za-z0-9+#\-\.]+")

def simple_tokens(text: str) -> List[str]:
    toks = [t.lower() for t in TOKEN_RE.findall(text)]
    return [t for t in toks if len(t) > 1 and t not in STOPWORDS]

def keyword_set(text: str) -> set:
    toks = simple_tokens(text)
    return set([t for t in toks if any(c.isalpha() for c in t) and len(t) >= 3])

def keyword_coverage(resume_text: str, jd_text: str) -> float:
    rset = keyword_set(resume_text)
    jset = keyword_set(jd_text)
    if not jset:
        return 0.0
    hits = len(jset & rset)
    return hits / len(jset)

def weighted_keyword_coverage(resume_text: str, jd_terms: Dict[str, List[str]]) -> float:
    weights = {"tools":3, "skills":2, "responsibilities":2, "domains":2, "certifications":1, "seniority":1}
    res_lower = resume_text.lower()
    total_weight = 0
    hit_weight = 0
    for cat, terms in jd_terms.items():
        w = weights.get(cat, 1)
        for t in terms:
            t_norm = t.lower().strip()
            if not t_norm:
                continue
            total_weight += w
            if t_norm in res_lower:
                hit_weight += w
    if total_weight == 0:
        return 0.0
    return hit_weight / total_weight

def top_terms(text: str, k: int = 25) -> List[str]:
    toks = [t for t in simple_tokens(text) if any(c.isalpha() for c in t) and len(t) >= 3]
    freq = Counter(toks)
    return [t for t, _ in freq.most_common(k)]

# -------------------- OpenAI helpers: distill + extract terms --------------------
_distill_cache: Dict[str, str] = {}
_terms_cache: Dict[str, Dict[str, List[str]]] = {}

def jd_hash(jd_text: str) -> str:
    return hashlib.sha256(jd_text.encode("utf-8")).hexdigest()

def llm_distill_jd(jd_text: str) -> str:
    if not client or not jd_text.strip():
        return jd_text
    h = jd_hash(jd_text)
    if h in _distill_cache:
        return _distill_cache[h]
    prompt = f"""Distill the JOB DESCRIPTION into a focused role core (8–12 bullet-like lines), excluding all perks/benefits, compensation, culture, location, legal/EEO, and company boilerplate.
Include only: core responsibilities, required skills and tools, domain focus, and seniority/scope signals.
Return plain text only. No intro or outro.

JOB DESCRIPTION:
{jd_text}
"""
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )
    distilled = (r.choices[0].message.content or "").strip()
    if not distilled or len(distilled) < 40:
        distilled = jd_text
    _distill_cache[h] = distilled
    return distilled

def llm_extract_terms(jd_text: str) -> Dict[str, List[str]]:
    if not client or not jd_text.strip():
        return {"skills": [], "tools": [], "domains": [], "responsibilities": [], "seniority": [], "certifications": []}
    h = "terms:" + jd_hash(jd_text)
    if h in _terms_cache:
        return _terms_cache[h]
    prompt = f"""Extract only role-critical keywords from the JOB DESCRIPTION as strict JSON.
Exclude benefits, perks, location, compensation, culture, legal, EEO, and boilerplate.
Groups:
- skills: capabilities (e.g., stakeholder management, roadmap ownership)
- tools: tech/frameworks/languages/platforms (e.g., SQL, Snowflake, Figma, Kubernetes)
- domains: industries/problems (e.g., fintech risk, B2B SaaS analytics)
- responsibilities: core duties (e.g., OKR planning, A/B testing)
- seniority: indicators (e.g., lead, principal, staff, manager)
- certifications: formal certs (e.g., PMP, AWS SA Pro)
- AVOID boilerplate soft skills like "effective communicatoin"

Output JSON ONLY with those keys and arrays. No prose.

JOB DESCRIPTION:
{jd_text}
"""
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )
    raw = (r.choices[0].message.content or "").strip()
    data = {}
    try:
        data = loads(raw)
    except Exception:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json", "", 1).strip()
        data = loads(cleaned)
    out = {k: sorted(set([t.strip() for t in data.get(k, []) if isinstance(t, str) and t.strip()])) for k in
           ["skills","tools","domains","responsibilities","seniority","certifications"]}
    _terms_cache[h] = out
    return out

# -------------------- Embedding + scoring --------------------
def embed(text: str) -> List[float]:
    if not client:
        return []
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding

def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    s = sum(x*y for x, y in zip(a, b))
    na = sum(x*x for x in a) ** 0.5
    nb = sum(y*y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return s / (na * nb)

def llm_fit_score(resume_text: str, jd_text: str) -> float:
    if not client:
        return 0.0
    prompt = f"""You are a strict recruiter. Score how well the RESUME matches the JOB DESCRIPTION on a 0–100 scale.
Rules:
- Consider skill and domain alignment, scope, seniority, quantified impact, tools/tech, and responsibilities.
- Do NOT reward content not present in the resume text.
- Return ONLY a number 0–100, no commentary.

JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_text}
"""
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role":"user","content":prompt}],
        temperature=0
    )
    out = (r.choices[0].message.content or "").strip()
    m = re.search(r"(\d{1,3})", out)
    if not m:
        return 0.0
    val = int(m.group(1))
    val = max(0, min(100, val))
    return float(val)

def composite_score(resume_text: str, jd_text: str) -> dict:
    jd_for_terms = jd_text
    jd_for_embed = jd_text

    if USE_DISTILLED_JD:
        distilled = llm_distill_jd(jd_text)
        jd_for_embed = distilled
    else:
        distilled = None

    # semantic similarity: mix distilled and original for stability
    emb_r = embed(resume_text)
    emb_j_dist = embed(jd_for_embed)
    sim_dist = cosine(emb_r, emb_j_dist)
    sim_orig = cosine(emb_r, embed(jd_text)) if USE_DISTILLED_JD else sim_dist
    semantic = W_DISTILLED * sim_dist + (1.0 - W_DISTILLED) * sim_orig

    # keyword coverage
    if USE_LLM_TERMS:
        jd_for_terms = distilled if (USE_DISTILLED_JD and distilled) else jd_text
        terms = llm_extract_terms(jd_for_terms)
        key = weighted_keyword_coverage(resume_text, terms)
    else:
        key = keyword_coverage(resume_text, jd_text)

    # llm rubric
    llm = llm_fit_score(resume_text, jd_for_terms) / 100.0

    score = W_EMB*semantic + W_KEY*key + W_LLM*llm
    out = {
        "embed_sim": round(semantic, 4),
        "keyword_cov": round(key, 4),
        "llm_score": round(llm*100.0, 1),
        "composite": round(score*100.0, 1),
    }
    if USE_DISTILLED_JD:
        out["distilled_used"] = True
    if USE_LLM_TERMS:
        out["llm_terms_used"] = True
    return out

# -------------------- Rewrite prompt (JD-term targeted; uses distilled JD when enabled) --------------------
def rewrite_with_openai(bullets: List[str], job_description: str) -> List[str]:
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")

    jd_for_terms = job_description
    if USE_DISTILLED_JD:
        distilled = llm_distill_jd(job_description)
        jd_for_terms = distilled

    if USE_LLM_TERMS:
        jd_terms_struct = llm_extract_terms(jd_for_terms)
        terms_flat = []
        for cat in ["tools","skills","responsibilities","domains","certifications","seniority"]:
            terms_flat.extend(jd_terms_struct.get(cat, []))
    else:
        terms_flat = top_terms(jd_for_terms, k=25)

    terms_line = ", ".join(terms_flat[:40])

    prompt = f"""You are an expert resume editor.
For each bullet:
- Preserve facts and metrics. Do not invent.
- Align to the role by adding 2–4 high-value terms from the list if they truthfully apply. Prefer exact phrases over synonyms when accurate. Do not add boilerplate soft skills.
- Structure: outcome → metric → tool/domain term.
- Keep concise and impactful. Avoid filler. Do not change tense/person.

Role-critical terms to consider (use only if accurate):
{terms_line}

Original bullets:
{chr(10).join(f"- {b}" for b in bullets)}

Return only the rewritten bullets, one per line, same order, no numbering, no extra text."""
    log.info(f"OpenAI request: bullets={len(bullets)} jd_terms={len(terms_flat)} distilled_used={USE_DISTILLED_JD} llm_terms_used={USE_LLM_TERMS}")
    r = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    text = r.choices[0].message.content.strip()
    lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
    log.info(f"OpenAI response lines: {len(lines)}")
    return lines

# -------------------- Endpoint: rewrite (DOCX) --------------------
@app.post("/rewrite")
async def rewrite(
    file: UploadFile = File(...),
    job_description: str = Form(...),
    max_chars_override: Optional[int] = Form(None)
):
    raw = await file.read()
    size = len(raw)
    ct = file.content_type
    sha = hashlib.sha256(raw).hexdigest()
    log.info(f"/rewrite: recv filename='{file.filename}' ct='{ct}' size={size} sha256={sha} jd_len={len(job_description)} override={max_chars_override}")

    if not raw or size < 512:
        return JSONResponse({"error":"empty_or_small_file"}, status_code=400)
    if ct not in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/msword",
    }:
        return JSONResponse({"error":"bad_content_type","got":ct}, status_code=415)

    try:
        doc = Document(BytesIO(raw))
    except Exception as e:
        log.exception("bad_docx")
        return JSONResponse({"error":"bad_docx","detail":str(e)}, status_code=400)

    bullets, paras = collect_word_numbered_bullets(doc)
    if not bullets:
        return JSONResponse({"error":"no_bullets_found"}, status_code=422)

    try:
        rewritten = rewrite_with_openai(bullets, job_description)
    except Exception as e:
        log.exception("openai_failed")
        return JSONResponse({"error":"openai_failed","detail":str(e)}, status_code=502)

    if len(rewritten) != len(paras):
        return JSONResponse({"error":"bullet_count_mismatch","in":len(paras),"out":len(rewritten)}, status_code=500)

    edited = 0
    for idx, (p, orig, new_text) in enumerate(zip(paras, bullets, rewritten)):
        cap = tiered_char_cap(len(orig), max_chars_override)
        fitted = enforce_char_cap_with_reprompt(new_text, cap)
        set_paragraph_text_with_selective_links(p, fitted)
        log.info(f"bullet[{idx}] orig_len={len(orig)} cap={cap} final_len={len(fitted)}")
        edited += 1

    enforce_single_page(doc)
    buf = BytesIO(); doc.save(buf); data = buf.getvalue()
    log.info(f"Returning DOCX bytes={len(data)} sha256={hashlib.sha256(data).hexdigest()}")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="resume_edited.docx"'}
    )

# -------------------- Endpoint: rewrite_json (JSON + base64 DOCX + scores) --------------------
@app.post("/rewrite_json")
async def rewrite_json(
    file: UploadFile = File(...),
    job_description: str = Form(...),
    max_chars_override: Optional[int] = Form(None),
    chars_per_line: Optional[int] = Form(None),
    tier_slack: Optional[int] = Form(None),
):
    raw = await file.read()
    size = len(raw)
    ct = file.content_type
    sha = hashlib.sha256(raw).hexdigest()

    log.info(f"/rewrite_json recv file='{file.filename}' size={size} sha256={sha} override={max_chars_override} llm_terms={USE_LLM_TERMS} distilled={USE_DISTILLED_JD}")

    if not raw or size < 512:
        return JSONResponse({"error":"empty_or_small_file"}, status_code=400)
    if ct not in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/msword",
    }:
        return JSONResponse({"error":"bad_content_type","got":ct}, status_code=415)

    try:
        doc = Document(BytesIO(raw))
    except Exception as e:
        log.exception("bad_docx")
        return JSONResponse({"error":"bad_docx","detail":str(e)}, status_code=400)

    bullets, paras = collect_word_numbered_bullets(doc)
    if not bullets:
        return JSONResponse({"error":"no_bullets_found"}, status_code=422)

    # BEFORE scores
    resume_before = "\n".join(bullets)
    try:
        score_before = composite_score(resume_before, job_description)
    except Exception as e:
        log.exception("score_before_failed")
        score_before = {"embed_sim": 0.0, "keyword_cov": 0.0, "llm_score": 0.0, "composite": 0.0, "error": str(e)}

    # Rewrite
    try:
        rewritten = rewrite_with_openai(bullets, job_description)
    except Exception as e:
        log.exception("openai_failed")
        return JSONResponse({"error":"openai_failed","detail":str(e)}, status_code=502)

    if len(rewritten) != len(paras):
        return JSONResponse({"error":"bullet_count_mismatch","in":len(paras),"out":len(rewritten)}, status_code=500)

    # Enforce caps and write into doc
    final_texts = []
    for idx, (p, orig, new_text) in enumerate(zip(paras, bullets, rewritten)):
        cap = tiered_char_cap(len(orig), max_chars_override)
        fitted = enforce_char_cap_with_reprompt(new_text, cap)
        set_paragraph_text_with_selective_links(p, fitted)
        final_texts.append(fitted)
        log.info(f"bullet[{idx}] orig_len={len(orig)} cap={cap} final_len={len(fitted)}")

    # AFTER scores
    resume_after = "\n".join(final_texts)
    try:
        score_after = composite_score(resume_after, job_description)
    except Exception as e:
        log.exception("score_after_failed")
        score_after = {"embed_sim": 0.0, "keyword_cov": 0.0, "llm_score": 0.0, "composite": 0.0, "error": str(e)}

    # Serialize DOCX
    enforce_single_page(doc)
    buf = BytesIO(); doc.save(buf); data = buf.getvalue()
    b64 = base64.b64encode(data).decode("ascii")

    # Delta
    try:
        delta = {
            "embed_sim": round(score_after["embed_sim"] - score_before["embed_sim"], 4),
            "keyword_cov": round(score_after["keyword_cov"] - score_before["keyword_cov"], 4),
            "llm_score": round(score_after["llm_score"] - score_before["llm_score"], 1),
            "composite": round(score_after["composite"] - score_before["composite"], 1),
        }
    except Exception:
        delta = {}

    # Include distilled JD preview when enabled to aid debugging
    distilled_preview = llm_distill_jd(job_description) if USE_DISTILLED_JD else None

    return JSONResponse({
        "file_b64": b64,
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "filename": "resume_edited.docx",
        "scores": {
            "before": score_before,
            "after": score_after,
            "delta": delta
        },
        "meta": {
            "use_llm_terms": USE_LLM_TERMS,
            "use_distilled_jd": USE_DISTILLED_JD,
            "semantic_distilled_weight": W_DISTILLED,
            "distilled_jd": distilled_preview
        }
    })