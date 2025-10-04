import os
import logging
import hashlib
from io import BytesIO
from copy import deepcopy
from typing import List, Tuple
import sys

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

# -------------------- Globals --------------------
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

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
    return {"status": "ok", "openai": bool(OPENAI_KEY)}

# -------------------- Word helpers --------------------
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
        r_id = h.get(qn("r:id"))
        url = None
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
    lower = new_text.lower()
    spans, i = [], 0
    while i < len(new_text):
        match = None
        for lk in anchors:
            a = lk["text"]
            al = a.lower()
            if lower.startswith(al, i):
                match = (i, i + len(a), lk)
                break
        if match:
            spans.append(match)
            i = match[1]
        else:
            next_pos = len(new_text)
            for lk in anchors:
                j = lower.find(lk["text"].lower(), i)
                if j != -1:
                    next_pos = min(next_pos, j)
            spans.append((i, next_pos, None))
            i = next_pos
    for child in list(p_el):
        if child.tag != f"{{{W_NS}}}pPr":
            p_el.remove(child)
    for start, end, lk in spans:
        seg = new_text[start:end]
        if not seg:
            continue
        p_el.append(
            _make_hyperlink_run(p, seg, lk["url"], lk["rPr"] or tmpl) if lk else _make_run(seg, tmpl)
        )

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
    while len(_body_p()) > 1 and not doc.paragraphs[-1].text.strip():
        body.remove(doc.paragraphs[-1]._element)

# -------------------- Character Cap Enforcement --------------------
def get_char_cap(original_len: int, override: int = None) -> int:
    if override:
        return override
    if original_len <= 110:
        return 100
    elif original_len <= 210:
        return 200
    else:
        return 300

def enforce_char_cap_with_reprompt(text: str, cap: int) -> str:
    cur = text.strip().lstrip("-• ").strip()
    tries = 0
    while len(cur) > cap and tries < 3:
        prompt = (
            f"Rewrite this resume bullet in {cap} characters or fewer. "
            f"Preserve numbers and core results. No fluff. Return only the bullet.\n\nBullet:\n{cur}"
        )
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        cur = r.choices[0].message.content.strip().lstrip("-• ").strip()
        tries += 1
    if len(cur) > cap:
        cur = cur[:cap].rstrip()
    return cur

# -------------------- OpenAI call --------------------
def rewrite_with_openai(bullets: List[str], job_description: str) -> List[str]:
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")
    prompt = f"""You are an expert resume editor.
Rewrite each bullet to emphasize outcomes, impact, and quantifiable results.
Align language directly to the Job Description by naturally incorporating its key terms and phrases.
Preserve facts, metrics, and scope. Do not invent achievements. Keep voice, tense, and person consistent with the original.
Optimize for ATS scanning: clear action verbs, nouns from the JD, minimal fluff.

Job Description:
{job_description}

Bullets:
{chr(10).join(f"- {b}" for b in bullets)}

Return only the rewritten bullets, one per line, in the same order. No numbering. No extra text."""
    log.info(f"OpenAI request: bullets={len(bullets)}, jd_chars={len(job_description)}")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    text = r.choices[0].message.content.strip()
    lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
    log.info(f"OpenAI response lines: {len(lines)}")
    return lines

# -------------------- Main endpoint --------------------
@app.post("/rewrite")
async def rewrite(file: UploadFile = File(...), job_description: str = Form(...), max_chars_override: int = Form(None)):
    raw = await file.read()
    try:
        doc = Document(BytesIO(raw))
    except Exception as e:
        log.exception("Failed to open DOCX")
        return JSONResponse({"error": "bad_docx", "detail": str(e)}, status_code=400)

    bullets, paras = [], []
    for p in doc.paragraphs:
        pPr = p._p.pPr
        is_list = (
            (pPr is not None)
            and (getattr(pPr, "numPr", None) is not None)
            and (getattr(pPr.numPr, "numId", None) is not None)
            and (getattr(pPr.numPr.numId, "val", None) is not None)
        )
        if is_list and p.text.strip():
            bullets.append(p.text.strip())
            paras.append(p)

    if not bullets:
        return JSONResponse({"error": "no_bullets_found"}, status_code=422)

    rewritten = rewrite_with_openai(bullets, job_description)

    if len(rewritten) != len(paras):
        return JSONResponse({"error": "bullet_count_mismatch"}, status_code=500)

    edited = 0
    for idx, (p, orig, new_text) in enumerate(zip(paras, bullets, rewritten)):
        cap = get_char_cap(len(orig), max_chars_override)
        fitted = enforce_char_cap_with_reprompt(new_text, cap)
        set_paragraph_text_with_selective_links(p, fitted)
        log.info(f"Bullet {idx}: orig_len={len(orig)}, cap={cap}, final_len={len(fitted)}, text='{fitted[:80]}...'")
        edited += 1

    enforce_single_page(doc)
    buf = BytesIO()
    doc.save(buf)
    data = buf.getvalue()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="resume_edited.docx"'}
    )