import os
from io import BytesIO
from copy import deepcopy
from typing import List

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.enum.section import WD_SECTION_START

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your Lovable origin in production
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------- Word helpers ----------
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

# ---------- Model call ----------
def rewrite_with_openai(bullets: List[str], job_description: str) -> List[str]:
    prompt = f"""You are a professional resume writer. Rewrite the bullets for the job description.
Be concise and keep each bullet roughly the same length.

Job Description:
{job_description}

Bullets:
{chr(10).join(f"- {b}" for b in bullets)}

Return only rewritten bullets, one per line, no extra text."""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.7
    )
    text = r.choices[0].message.content.strip()
    return [line.strip("- ").strip() for line in text.splitlines() if line.strip()]

# ---------- Single endpoint for Lovable ----------
@app.post("/rewrite")
async def rewrite(file: UploadFile = File(...), job_description: str = Form(...)):
    raw = await file.read()
    doc = Document(BytesIO(raw))

    # collect bullet paragraphs
    bullets, paras = [], []
    for p in doc.paragraphs:
        pPr=p._p.pPr
        if not (pPr and pPr.numPr and pPr.numPr.numId and pPr.numPr.numId.val):
            continue
        text = p.text.strip()
        if text:
            bullets.append(text); paras.append(p)

    if not bullets:
        return {"error":"no bullets found"}

    rewritten = rewrite_with_openai(bullets, job_description)
    if len(rewritten) != len(paras):
        return {"error":"bullet count mismatch"}

    for p,new_text in zip(paras, rewritten):
        set_paragraph_text_with_selective_links(p, new_text)

    enforce_single_page(doc)
    out_buf = BytesIO(); doc.save(out_buf); out_buf.seek(0)
    return StreamingResponse(
        out_buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="resume_edited.docx"'}
    )