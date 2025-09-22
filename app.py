import os
import logging
import hashlib
from io import BytesIO
from copy import deepcopy
from typing import List

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
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("resume")

# -------------------- Globals --------------------
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# -------------------- FastAPI --------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# -------------------- Health --------------------
@app.get("/")
def root():
    return {"status": "ok", "openai": bool(OPENAI_KEY)}

# -------------------- Debug: echo upload bytes --------------------
@app.post("/echo")
async def echo(file: UploadFile = File(...)):
    data = await file.read()
    info = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    log.info(f"/echo: {info}")
    return JSONResponse(info)

# -------------------- Debug: structure probe (numbering, glyphs, tables) --------------------
@app.post("/probe2")
async def probe2(file: UploadFile = File(...)):
    BULLET_CHARS = {"•","·","-","–","—","◦","●","*"}
    raw = await file.read()
    try:
        d = Document(BytesIO(raw))
    except Exception as e:
        log.exception("Probe2: failed to open DOCX")
        return JSONResponse({"error": "bad_docx", "detail": str(e)}, status_code=400)

    # Numbering XML presence
    numpart = getattr(d.part, "numbering_part", None)
    ns = {"w": W_NS}
    num_counts = {"num": 0, "abstractNum": 0}
    if numpart is not None:
        root = numpart.element
        num_counts["num"] = len(root.findall(".//w:num", namespaces=ns))
        num_counts["abstractNum"] = len(root.findall(".//w:abstractNum", namespaces=ns))

    # Body paragraphs: numbered vs glyph-like
    total_body = len(d.paragraphs)
    word_list_count = 0
    glyph_like = 0
    glyph_samples = []
    for p in d.paragraphs:
        pPr = p._p.pPr
        is_list = (
            (pPr is not None)
            and (getattr(pPr, "numPr", None) is not None)
            and (getattr(pPr.numPr, "numId", None) is not None)
            and (getattr(pPr.numPr.numId, "val", None) is not None)
        )
        if is_list:
            word_list_count += 1
        t = p.text.strip()
        if t and t[0] in BULLET_CHARS:
            glyph_like += 1
            if len(glyph_samples) < 5:
                glyph_samples.append(t[:120])

    # Paragraphs inside tables
    table_paras = 0
    table_samples = []
    for tbl in d.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    table_paras += 1
                    if len(table_samples) < 5 and p.text.strip():
                        table_samples.append(p.text.strip()[:120])

    info = {
        "numbering_part_present": numpart is not None,
        "numbering_xml_counts": num_counts,
        "total_body_paragraphs": total_body,
        "word_numbered_list_paragraphs": word_list_count,
        "glyph_like_bullets_count": glyph_like,
        "glyph_like_samples": glyph_samples,
        "table_paragraphs_count": table_paras,
        "table_paragraph_samples": table_samples,
    }
    log.info(f"/probe2: {info}")
    return JSONResponse(info)

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
        r_id = h.get(qn('r:id')); url = None
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
    r = OxmlElement('w:r')
    if rPr_template is not None:
        r.append(deepcopy(rPr_template))
    t = OxmlElement('w:t'); t.set(qn('xml:space'), 'preserve'); t.text = text
    r.append(t); return r

def _make_hyperlink_run(p, text, url, rPr_template=None):
    r_id = p.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement('w:hyperlink'); h.set(qn('r:id'), r_id)
    h.append(_make_run(text, rPr_template)); return h

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
    # remove explicit page breaks and pageBreakBefore
    for p in doc.paragraphs:
        for br in list(p._element.findall(f".//{{{W_NS}}}br")):
            if br.get(qn('w:type')) == 'page':
                br.getparent().remove(br)
        pPr = p._p.pPr
        if pPr is not None:
            for pb in list(pPr.findall(f"./{{{W_NS}}}pageBreakBefore")):
                pPr.remove(pb)
    # make all sections continuous
    for sectPr in body.findall(f".//{{{W_NS}}}sectPr"):
        t = sectPr.find(f"./{{{W_NS}}}type") or OxmlElement('w:type')
        t.set(qn('w:val'), 'continuous')
        if t.getparent() is None: sectPr.append(t)
    try:
        if doc.sections:
            doc.sections[-1].start_type = WD_SECTION_START.CONTINUOUS
    except Exception:
        pass
    # trim trailing empties
    def _body_p(): return body.findall(f"./{{{W_NS}}}p")
    while len(_body_p())>1 and not doc.paragraphs[-1].text.strip():
        body.remove(doc.paragraphs[-1]._element)

# -------------------- OpenAI call --------------------
def rewrite_with_openai(bullets: List[str], job_description: str) -> List[str]:
    if not client:
        raise RuntimeError("OPENAI_API_KEY missing")
    prompt = f"""You are a professional resume writer. Rewrite the bullets for the job description.
Be concise and keep each bullet roughly the same length.

Job Description:
{job_description}

Bullets:
{chr(10).join(f"- {b}" for b in bullets)}

Return only rewritten bullets, one per line, no extra text."""
    log.info(f"OpenAI request: bullets={len(bullets)}, jd_chars={len(job_description)}")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.7
    )
    text = r.choices[0].message.content.strip()
    lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
    log.info(f"OpenAI response lines: {len(lines)}")
    return lines

# -------------------- Main endpoint --------------------
@app.post("/rewrite")
async def rewrite(file: UploadFile = File(...), job_description: str = Form(...)):
    # Read upload
    raw = await file.read()
    size = len(raw)
    ct = file.content_type
    sha = hashlib.sha256(raw).hexdigest()
    log.info(f"/rewrite: recv filename='{file.filename}' ct='{ct}' size={size} sha256={sha} jd_len={len(job_description)}")

    # Validate upload
    if not raw or size < 512:
        log.warning("Upload too small or empty")
        return JSONResponse({"error": "empty_or_small_file", "size": size}, status_code=400)
    if ct not in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/msword",
    }:
        log.warning(f"Unexpected content-type: {ct}")
        return JSONResponse({"error": "bad_content_type", "got": ct}, status_code=415)

    # Open DOCX
    try:
        doc = Document(BytesIO(raw))
    except Exception as e:
        log.exception("Failed to open DOCX")
        return JSONResponse({"error": "bad_docx", "detail": str(e)}, status_code=400)

    # Collect bullets (strict Word-numbered lists in body)
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
            bullets.append(text); paras.append(p)

    log.info(f"Bullet discovery: total_paragraphs={len(doc.paragraphs)} list_paragraphs={len(paras)}")

    if not bullets:
        sample = [p.text.strip() for p in doc.paragraphs[:5]]
        log.warning(f"No bullets found. First_paragraphs_sample={sample}")
        return JSONResponse({"error": "no_bullets_found"}, status_code=422)

    # Rewrite
    try:
        rewritten = rewrite_with_openai(bullets, job_description)
    except Exception as e:
        log.exception("OpenAI call failed")
        return JSONResponse({"error": "openai_failed", "detail": str(e)}, status_code=502)

    if len(rewritten) != len(paras):
        log.error(f"Bullet count mismatch: in={len(paras)} out={len(rewritten)}")
        return JSONResponse({"error": "bullet_count_mismatch", "in": len(paras), "out": len(rewritten)}, status_code=500)

    # Apply edits
    edited = 0
    for p, new_text in zip(paras, rewritten):
        try:
            set_paragraph_text_with_selective_links(p, new_text)
            edited += 1
        except Exception as e:
            log.exception("Failed applying paragraph edit")
            return JSONResponse({"error": "apply_failed", "detail": str(e)}, status_code=500)

    log.info(f"Applied edits to {edited} paragraphs")

    # Layout cleanup
    try:
        enforce_single_page(doc)
    except Exception as e:
        log.exception("enforce_single_page failed")
        return JSONResponse({"error": "layout_failed", "detail": str(e)}, status_code=500)

    # Save DOCX
    try:
        buf = BytesIO(); doc.save(buf); data = buf.getvalue()
        log.info(f"Returning DOCX bytes={len(data)} sha256={hashlib.sha256(data).hexdigest()}")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="resume_edited.docx"'}
        )
    except Exception as e:
        log.exception("Failed to serialize DOCX")
        return JSONResponse({"error": "serialize_failed", "detail": str(e)}, status_code=500)