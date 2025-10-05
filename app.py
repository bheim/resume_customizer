import os, hashlib, base64
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from config import log, health
from docx_utils import load_docx, collect_word_numbered_bullets, set_paragraph_text_with_selective_links, enforce_single_page
from llm_utils import rewrite_with_openai
from caps import tiered_char_cap, enforce_char_cap_with_reprompt
from scoring import composite_score

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["POST","GET","OPTIONS"], allow_headers=["*"])

@app.get("/")
def root():
    return health()

@app.post("/rewrite")
async def rewrite(file: UploadFile = File(...), job_description: str = Form(...), max_chars_override: Optional[int] = Form(None)):
    raw = await file.read()
    size = len(raw); ct = file.content_type; sha = hashlib.sha256(raw).hexdigest()
    log.info(f"/rewrite recv filename='{file.filename}' size={size} sha256={sha} override={max_chars_override}")
    if not raw or size < 512: return JSONResponse({"error":"empty_or_small_file"}, status_code=400)
    if ct not in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/octet-stream","application/msword"}:
        return JSONResponse({"error":"bad_content_type","got":ct}, status_code=415)
    try:
        doc = load_docx(raw)
    except Exception as e:
        log.exception("bad_docx"); return JSONResponse({"error":"bad_docx","detail":str(e)}, status_code=400)

    bullets, paras = collect_word_numbered_bullets(doc)
    if not bullets: return JSONResponse({"error":"no_bullets_found"}, status_code=422)
    log.info(f"bullets_in={len(bullets)} sample_in={[b[:60] for b in bullets[:3]]}")

    try:
        rewritten = rewrite_with_openai(bullets, job_description)
    except Exception as e:
        log.exception("openai_failed"); return JSONResponse({"error":"openai_failed","detail":str(e)}, status_code=502)

    log.info(f"bullets_out={len(rewritten)} sample_out={[r[:60] for r in rewritten[:3]]}")
    if len(rewritten) != len(paras):
        return JSONResponse({"error":"bullet_count_mismatch","in":len(paras),"out":len(rewritten)}, status_code=500)

    final_texts = []
    for idx, (p, orig, new_text) in enumerate(zip(paras, bullets, rewritten)):
        cap = tiered_char_cap(len(orig), max_chars_override)
        fitted = enforce_char_cap_with_reprompt(new_text, cap)
        set_paragraph_text_with_selective_links(p, fitted)
        final_texts.append(fitted)
        log.info(f"bullet[{idx}] orig_len={len(orig)} cap={cap} final_len={len(fitted)}")

    enforce_single_page(doc)
    from io import BytesIO
    buf = BytesIO(); doc.save(buf); data = buf.getvalue()
    log.info(f"Returning DOCX bytes={len(data)} sha256={hashlib.sha256(data).hexdigest()}")
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="resume_edited.docx"'})

@app.post("/rewrite_json")
async def rewrite_json(file: UploadFile = File(...), job_description: str = Form(...), max_chars_override: Optional[int] = Form(None)):
    raw = await file.read()
    size = len(raw); ct = file.content_type; sha = hashlib.sha256(raw).hexdigest()
    log.info(f"/rewrite_json recv file='{file.filename}' size={size} sha256={sha}")
    if not raw or size < 512: return JSONResponse({"error":"empty_or_small_file"}, status_code=400)
    if ct not in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/octet-stream","application/msword"}:
        return JSONResponse({"error":"bad_content_type","got":ct}, status_code=415)
    try:
        doc = load_docx(raw)
    except Exception as e:
        log.exception("bad_docx"); return JSONResponse({"error":"bad_docx","detail":str(e)}, status_code=400)

    bullets, paras = collect_word_numbered_bullets(doc)
    if not bullets: return JSONResponse({"error":"no_bullets_found"}, status_code=422)

    resume_before = "\n".join(bullets)
    try:
        score_before = composite_score(resume_before, job_description)
    except Exception as e:
        score_before = {"embed_sim":0.0,"keyword_cov":0.0,"llm_score":0.0,"composite":0.0,"error":str(e)}

    try:
        rewritten = rewrite_with_openai(bullets, job_description)
    except Exception as e:
        log.exception("openai_failed"); return JSONResponse({"error":"openai_failed","detail":str(e)}, status_code=502)

    if len(rewritten) != len(paras):
        return JSONResponse({"error":"bullet_count_mismatch","in":len(paras),"out":len(rewritten)}, status_code=500)

    final_texts = []
    for idx, (p, orig, new_text) in enumerate(zip(paras, bullets, rewritten)):
        cap = tiered_char_cap(len(orig), max_chars_override)
        fitted = enforce_char_cap_with_reprompt(new_text, cap)
        set_paragraph_text_with_selective_links(p, fitted)
        final_texts.append(fitted)

    resume_after = "\n".join(final_texts)
    try:
        score_after = composite_score(resume_after, job_description)
    except Exception as e:
        score_after = {"embed_sim":0.0,"keyword_cov":0.0,"llm_score":0.0,"composite":0.0,"error":str(e)}

    enforce_single_page(doc)
    from io import BytesIO
    buf = BytesIO(); doc.save(buf); data = buf.getvalue()
    b64 = base64.b64encode(data).decode("ascii")

    delta = {}
    try:
        delta = {
            "embed_sim": round(score_after["embed_sim"] - score_before["embed_sim"], 4),
            "keyword_cov": round(score_after["keyword_cov"] - score_before["keyword_cov"], 4),
            "llm_score": round(score_after["llm_score"] - score_before["llm_score"], 1),
            "composite": round(score_after["composite"] - score_before["composite"], 1),
        }
    except Exception: pass

    return JSONResponse({
        "file_b64": b64,
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "filename": "resume_edited.docx",
        "scores": {"before": score_before, "after": score_after, "delta": delta}
    })