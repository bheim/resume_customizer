import os, hashlib, base64
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from config import log, health, supabase
from docx_utils import load_docx, collect_word_numbered_bullets, set_paragraph_text_with_selective_links, enforce_single_page
from llm_utils import rewrite_with_openai, generate_followup_questions, should_ask_more_questions, rewrite_with_context
from caps import tiered_char_cap, enforce_char_cap_with_reprompt
from scoring import composite_score
from db_utils import (create_qa_session, get_qa_session, store_qa_pair, update_qa_answer,
                      get_session_qa_pairs, get_user_context, store_user_context,
                      update_session_status, get_answered_qa_pairs)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["POST","GET","OPTIONS"], allow_headers=["*"])


# Pydantic models for Q&A endpoints
class AnswerSubmission(BaseModel):
    session_id: str
    answers: List[dict]  # List of {"qa_id": "...", "answer": "..."}
    user_id: Optional[str] = None


@app.get("/")
def root():
    return health()

@app.post("/rewrite")
async def rewrite(file: UploadFile = File(...), job_description: str = Form(...), max_chars_override: Optional[int] = Form(None)):
    raw = await file.read()
    size = len(raw); ct = file.content_type; sha = hashlib.sha256(raw).hexdigest()
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

    enforce_single_page(doc)
    from io import BytesIO
    buf = BytesIO(); doc.save(buf); data = buf.getvalue()
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


@app.post("/generate_questions")
async def generate_questions(file: UploadFile = File(...), job_description: str = Form(...), user_id: Optional[str] = Form(None)):
    """
    Generate initial follow-up questions based on resume bullets and job description.
    Creates a Q&A session in Supabase and returns questions for the frontend to display.
    """
    if not supabase:
        return JSONResponse({"error": "supabase_not_configured", "detail": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY."}, status_code=503)

    # Read and validate file
    raw = await file.read()
    size = len(raw)
    ct = file.content_type
    log.info(f"/generate_questions recv file='{file.filename}' size={size}")

    if not raw or size < 512:
        return JSONResponse({"error": "empty_or_small_file"}, status_code=400)

    if ct not in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                  "application/octet-stream", "application/msword"}:
        return JSONResponse({"error": "bad_content_type", "got": ct}, status_code=415)

    # Parse DOCX
    try:
        doc = load_docx(raw)
    except Exception as e:
        log.exception("bad_docx")
        return JSONResponse({"error": "bad_docx", "detail": str(e)}, status_code=400)

    bullets, paras = collect_word_numbered_bullets(doc)
    if not bullets:
        return JSONResponse({"error": "no_bullets_found"}, status_code=422)

    log.info(f"Found {len(bullets)} bullets")

    # Check for existing user context to avoid repeat questions
    existing_context = []
    if user_id and user_id != "anonymous":
        user_context = get_user_context(user_id)
        existing_context = [{"question": ctx["question"], "answer": ctx["answer"]} for ctx in user_context]
        log.info(f"Found {len(existing_context)} existing Q&A pairs for user")

    # Create Q&A session
    session_id = create_qa_session(user_id, job_description, bullets)
    if not session_id:
        return JSONResponse({"error": "failed_to_create_session"}, status_code=500)

    # Generate questions using LLM
    try:
        questions = generate_followup_questions(bullets, job_description, existing_context, max_questions=3)
    except Exception as e:
        log.exception("Failed to generate questions")
        return JSONResponse({"error": "question_generation_failed", "detail": str(e)}, status_code=502)

    # Store questions in database
    qa_pairs = []
    for q in questions:
        qa_id = store_qa_pair(session_id, q["question"], question_type=q["type"])
        if qa_id:
            log.info(f"Created qa_pair with ID: {qa_id} for question: {q['question'][:50]}...")
            qa_pairs.append({
                "qa_id": qa_id,
                "question": q["question"],
                "type": q["type"]
            })
        else:
            log.error(f"Failed to store qa_pair for question: {q['question'][:50]}...")

    log.info(f"Generated {len(qa_pairs)} questions for session {session_id}")
    log.info(f"Returning qa_ids to frontend: {[qp['qa_id'] for qp in qa_pairs]}")

    return JSONResponse({
        "session_id": session_id,
        "questions": qa_pairs,
        "bullet_count": len(bullets)
    })


@app.post("/submit_answers")
async def submit_answers(submission: AnswerSubmission = Body(...)):
    """
    Receive answers to follow-up questions and determine if more questions are needed.
    Stores answers in Supabase and optionally stores in user context.
    """
    if not supabase:
        return JSONResponse({"error": "supabase_not_configured"}, status_code=503)

    session_id = submission.session_id
    answers = submission.answers
    user_id = submission.user_id

    log.info(f"Received answers for session {session_id}")
    log.info(f"qa_ids received from frontend: {[ans.get('qa_id') for ans in answers]}")

    # Validate session exists
    session = get_qa_session(session_id)
    if not session:
        return JSONResponse({"error": "session_not_found"}, status_code=404)

    # Update answers in database
    for ans in answers:
        qa_id = ans.get("qa_id")
        answer_text = ans.get("answer", "").strip()

        if not qa_id or not answer_text:
            continue

        success = update_qa_answer(qa_id, answer_text)
        if not success:
            log.warning(f"Failed to update answer for qa_id={qa_id}")

    # Get all answered Q&A pairs
    all_qa_pairs = get_session_qa_pairs(session_id)
    answered_qa = [{"question": qa["question"], "answer": qa["answer"]}
                   for qa in all_qa_pairs if qa.get("answer")]

    log.info(f"Session {session_id} now has {len(answered_qa)} answered questions")

    # Store in user context if user_id provided
    if user_id and user_id != "anonymous":
        for qa in answered_qa:
            store_user_context(user_id, qa["question"], qa["answer"])

    # Determine if more questions are needed
    bullets = session["bullets"]
    job_description = session["job_description"]

    try:
        need_more, reason = should_ask_more_questions(answered_qa, bullets, job_description)
    except Exception as e:
        log.exception("Failed to determine if more questions needed")
        need_more = False
        reason = "Error determining question need"

    log.info(f"Need more questions: {need_more}. Reason: {reason}")

    # If more questions needed, generate them
    new_questions = []
    # HARDCODING TO CIRCUMVENT NEW QUESTIONS
    need_more = False
    if need_more:
        try:
            questions = generate_followup_questions(bullets, job_description, answered_qa, max_questions=2)

            for q in questions:
                qa_id = store_qa_pair(session_id, q["question"], question_type=q["type"])
                if qa_id:
                    new_questions.append({
                        "qa_id": qa_id,
                        "question": q["question"],
                        "type": q["type"]
                    })
        except Exception as e:
            log.exception("Failed to generate follow-up questions")

    # If no more questions needed, mark session as ready for rewriting
    if not need_more:
        update_session_status(session_id, "ready_for_rewrite")

    return JSONResponse({
        "session_id": session_id,
        "need_more_questions": need_more,
        "reason": reason,
        "new_questions": new_questions,
        "total_answered": len(answered_qa),
        "ready_for_rewrite": not need_more
    })


@app.post("/rewrite_with_qa")
async def rewrite_with_qa(session_id: str = Form(...), max_chars_override: Optional[int] = Form(None)):
    """
    Rewrite resume using both the job description and the Q&A context from the session.
    This endpoint should be called after the Q&A flow is complete.
    """
    if not supabase:
        return JSONResponse({"error": "supabase_not_configured"}, status_code=503)

    # Validate session exists
    session = get_qa_session(session_id)
    if not session:
        return JSONResponse({"error": "session_not_found"}, status_code=404)

    bullets = session["bullets"]
    job_description = session["job_description"]

    # Get answered Q&A pairs for context
    qa_context = get_answered_qa_pairs(session_id)

    if not qa_context:
        log.warning(f"No Q&A context found for session {session_id}, falling back to basic rewrite")
        # Fallback to basic rewrite without context
        try:
            rewritten = rewrite_with_openai(bullets, job_description)
        except Exception as e:
            log.exception("openai_failed")
            return JSONResponse({"error": "openai_failed", "detail": str(e)}, status_code=502)
    else:
        # Use Q&A context for better rewriting
        log.info(f"Using {len(qa_context)} Q&A pairs for context in rewrite")
        try:
            rewritten = rewrite_with_context(bullets, job_description, qa_context)
        except Exception as e:
            log.exception("openai_failed_with_context")
            return JSONResponse({"error": "openai_failed", "detail": str(e)}, status_code=502)

    # We need the original document to modify it
    # For now, return just the rewritten bullets as JSON
    # The frontend will need to provide the original file or we need to store it

    resume_before = "\n".join(bullets)
    try:
        score_before = composite_score(resume_before, job_description)
    except Exception as e:
        score_before = {"embed_sim": 0.0, "keyword_cov": 0.0, "llm_score": 0.0, "composite": 0.0, "error": str(e)}

    resume_after = "\n".join(rewritten)
    try:
        score_after = composite_score(resume_after, job_description)
    except Exception as e:
        score_after = {"embed_sim": 0.0, "keyword_cov": 0.0, "llm_score": 0.0, "composite": 0.0, "error": str(e)}

    delta = {}
    try:
        delta = {
            "embed_sim": round(score_after["embed_sim"] - score_before["embed_sim"], 4),
            "keyword_cov": round(score_after["keyword_cov"] - score_before["keyword_cov"], 4),
            "llm_score": round(score_after["llm_score"] - score_before["llm_score"], 1),
            "composite": round(score_after["composite"] - score_before["composite"], 1),
        }
    except Exception:
        pass

    # Mark session as completed
    update_session_status(session_id, "completed")

    return JSONResponse({
        "session_id": session_id,
        "original_bullets": bullets,
        "rewritten_bullets": rewritten,
        "scores": {"before": score_before, "after": score_after, "delta": delta},
        "qa_context_used": len(qa_context)
    })