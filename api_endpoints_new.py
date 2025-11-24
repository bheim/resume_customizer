"""
New API endpoints for persistent bullet storage and fact-based generation.

These endpoints implement the refactored onboarding and job application flows.
Integrate these into app.py or use as reference for implementation.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Dict, Optional
from pydantic import BaseModel
import tempfile
import os

# Import existing utilities
from docx_utils import collect_word_numbered_bullets
from llm_utils import (
    embed,
    extract_facts_from_qa,
    generate_bullet_with_facts,
    generate_followup_questions,
    should_ask_more_questions
)
from db_utils import (
    store_user_bullet,
    get_user_bullet,
    match_bullet_with_confidence,
    store_bullet_facts,
    get_bullet_facts,
    confirm_bullet_facts,
    update_bullet_facts,
    create_qa_session,
    get_answered_qa_pairs,
    store_qa_pair,
    update_qa_answer
)
from db_utils_optimized import match_bullet_with_confidence_optimized
from config import log

# Create router
router = APIRouter(prefix="/v2", tags=["Resume Optimizer V2"])


# =====================================================================
# Request/Response Models
# =====================================================================

class BulletMatch(BaseModel):
    bullet_index: int
    bullet_text: str
    match_type: str  # "exact" | "high_confidence" | "medium_confidence" | "no_match"
    bullet_id: Optional[str] = None
    similarity_score: Optional[float] = None
    existing_bullet_text: Optional[str] = None
    has_facts: bool = False


class OnboardingStartResponse(BaseModel):
    session_id: str
    bullets: List[str]
    bullet_matches: List[BulletMatch]
    message: str


class FactsExtractionResponse(BaseModel):
    bullet_id: str
    bullet_text: str
    extracted_facts: Dict
    fact_id: Optional[str] = None


class BulletGenerationRequest(BaseModel):
    user_id: str
    job_description: str
    bullets: List[str]


class BulletGenerationResponse(BaseModel):
    enhanced_bullets: List[str]
    bullets_with_facts: List[int]  # Indices of bullets that used stored facts
    bullets_without_facts: List[int]  # Indices that fell back to basic rewrite


# =====================================================================
# ONBOARDING ENDPOINTS
# =====================================================================

@router.post("/onboarding/start", response_model=OnboardingStartResponse)
async def start_onboarding(
    user_id: str = Form(...),
    resume_file: UploadFile = File(...),
    source_name: Optional[str] = Form(None)
):
    """
    Start onboarding process: extract bullets from resume and match against existing bullets.

    This is the first step in the onboarding flow. It:
    1. Extracts bullets from the uploaded resume
    2. For each bullet, checks if it already exists (exact or similar match)
    3. Returns match information for user confirmation

    Args:
        user_id: User identifier
        resume_file: Uploaded resume DOCX file
        source_name: Optional name for this resume (e.g., "Base Resume 2024")

    Returns:
        OnboardingStartResponse with session_id, bullets, and match information
    """
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            content = await resume_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Extract bullets from resume
        from docx import Document
        doc = Document(tmp_path)
        bullets, _ = collect_word_numbered_bullets(doc)

        # Clean up temp file
        os.unlink(tmp_path)

        if not bullets:
            raise HTTPException(status_code=400, detail="No bullets found in resume")

        log.info(f"Extracted {len(bullets)} bullets from resume for user {user_id}")

        # Create a session for this onboarding
        session_id = create_qa_session(user_id, "", bullets)
        if not session_id:
            raise HTTPException(status_code=500, detail="Failed to create session")

        # Match each bullet against existing bullets
        bullet_matches = []
        for idx, bullet in enumerate(bullets):
            # Generate embedding for matching
            embedding = embed(bullet)

            # Match bullet with confidence
            match_result = match_bullet_with_confidence(user_id, bullet, embedding)

            # Check if matched bullet has facts
            has_facts = False
            if match_result["bullet_id"]:
                facts = get_bullet_facts(match_result["bullet_id"], confirmed_only=True)
                has_facts = len(facts) > 0

            bullet_matches.append(BulletMatch(
                bullet_index=idx,
                bullet_text=bullet,
                match_type=match_result["match_type"],
                bullet_id=match_result["bullet_id"],
                similarity_score=match_result["similarity_score"],
                existing_bullet_text=match_result["existing_bullet_text"],
                has_facts=has_facts
            ))

        # Count match types
        exact_matches = sum(1 for m in bullet_matches if m.match_type == "exact")
        high_conf = sum(1 for m in bullet_matches if m.match_type == "high_confidence")
        medium_conf = sum(1 for m in bullet_matches if m.match_type == "medium_confidence")
        new_bullets = sum(1 for m in bullet_matches if m.match_type == "no_match")

        message = (
            f"Found {len(bullets)} bullets. "
            f"{exact_matches} exact matches, {high_conf} high confidence, "
            f"{medium_conf} medium confidence, {new_bullets} new."
        )

        return OnboardingStartResponse(
            session_id=session_id,
            bullets=bullets,
            bullet_matches=bullet_matches,
            message=message
        )

    except Exception as e:
        log.exception(f"Error in onboarding start: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onboarding/confirm_match")
async def confirm_bullet_match(
    user_id: str = Form(...),
    session_id: str = Form(...),
    bullet_index: int = Form(...),
    bullet_text: str = Form(...),
    matched_bullet_id: Optional[str] = Form(None),
    is_same_bullet: bool = Form(...)
):
    """
    User confirms if a similar bullet is the same as an existing one.

    If user confirms it's the same:
    - Link to existing bullet (no need to collect facts again)

    If user says it's different:
    - Store as new bullet
    - Return questions to collect facts

    Args:
        user_id: User identifier
        session_id: Session ID from onboarding/start
        bullet_index: Index of the bullet
        bullet_text: The bullet text
        matched_bullet_id: ID of the matched bullet (if any)
        is_same_bullet: User's confirmation (True = same, False = different)

    Returns:
        If same: Confirmation message
        If different: List of questions to collect facts
    """
    try:
        if is_same_bullet and matched_bullet_id:
            # Link to existing bullet
            log.info(f"User confirmed bullet {bullet_index} is same as {matched_bullet_id}")
            return {
                "status": "linked",
                "bullet_id": matched_bullet_id,
                "message": "Linked to existing bullet with facts"
            }
        else:
            # Store as new bullet
            embedding = embed(bullet_text)
            bullet_id = store_user_bullet(user_id, bullet_text, embedding)

            if not bullet_id:
                raise HTTPException(status_code=500, detail="Failed to store bullet")

            # Generate questions for this bullet
            questions = generate_followup_questions([bullet_text], "")  # No JD yet

            # Store questions in database
            for q in questions:
                store_qa_pair(
                    session_id,
                    q["question"],
                    None,
                    q.get("type"),
                    bullet_index
                )

            log.info(f"Stored new bullet {bullet_id} and generated {len(questions)} questions")

            return {
                "status": "new_bullet",
                "bullet_id": bullet_id,
                "questions": questions,
                "message": f"Generated {len(questions)} questions for new bullet"
            }

    except Exception as e:
        log.exception(f"Error confirming bullet match: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onboarding/extract_facts", response_model=FactsExtractionResponse)
async def extract_and_show_facts(
    session_id: str = Form(...),
    bullet_id: str = Form(...),
    bullet_text: str = Form(...)
):
    """
    Extract structured facts from Q&A conversation for user confirmation.

    This is called after the user has answered questions about a bullet.
    The extracted facts are shown to the user for confirmation/editing.

    Args:
        session_id: Session ID
        bullet_id: Bullet ID
        bullet_text: The bullet text

    Returns:
        FactsExtractionResponse with extracted facts
    """
    try:
        # Get answered Q&A pairs for this session
        qa_pairs = get_answered_qa_pairs(session_id)

        if not qa_pairs:
            raise HTTPException(status_code=400, detail="No answered questions found")

        # Extract facts from Q&A
        extracted_facts = extract_facts_from_qa(bullet_text, qa_pairs)

        # Store unconfirmed facts (user will confirm/edit next)
        fact_id = store_bullet_facts(
            bullet_id,
            extracted_facts,
            qa_session_id=session_id,
            confirmed=False
        )

        log.info(f"Extracted facts for bullet {bullet_id}: {fact_id}")

        return FactsExtractionResponse(
            bullet_id=bullet_id,
            bullet_text=bullet_text,
            extracted_facts=extracted_facts,
            fact_id=fact_id
        )

    except Exception as e:
        log.exception(f"Error extracting facts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onboarding/save_facts")
async def save_confirmed_facts(
    fact_id: str = Form(...),
    edited_facts: str = Form(...)  # JSON string
):
    """
    Save user-confirmed/edited facts.

    Args:
        fact_id: The fact ID from extract_facts
        edited_facts: User-edited facts as JSON string

    Returns:
        Confirmation message
    """
    try:
        import json
        facts = json.loads(edited_facts)

        # Update facts with user edits
        success = update_bullet_facts(fact_id, facts)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update facts")

        # Mark as confirmed
        confirmed = confirm_bullet_facts(fact_id)
        if not confirmed:
            raise HTTPException(status_code=500, detail="Failed to confirm facts")

        log.info(f"Saved and confirmed facts: {fact_id}")

        return {
            "status": "success",
            "message": "Facts saved and confirmed",
            "fact_id": fact_id
        }

    except Exception as e:
        log.exception(f"Error saving facts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# JOB APPLICATION ENDPOINTS
# =====================================================================

@router.post("/apply/match_bullets")
async def match_bullets_for_job(
    user_id: str = Form(...),
    resume_file: UploadFile = File(...)
):
    """
    Match bullets from uploaded resume to stored bullets with facts.

    This is the first step in the job application flow.

    Args:
        user_id: User identifier
        resume_file: Uploaded resume DOCX file

    Returns:
        List of bullets with match information and available facts
    """
    try:
        # Extract bullets from resume (same as onboarding)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            content = await resume_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        from docx import Document
        doc = Document(tmp_path)
        bullets, _ = collect_word_numbered_bullets(doc)
        os.unlink(tmp_path)

        if not bullets:
            raise HTTPException(status_code=400, detail="No bullets found in resume")

        # Match each bullet
        matches = []
        for idx, bullet in enumerate(bullets):
            embedding = embed(bullet)
            match_result = match_bullet_with_confidence_optimized(user_id, bullet, embedding)

            # Get facts if match found
            facts = None
            if match_result["bullet_id"]:
                fact_records = get_bullet_facts(match_result["bullet_id"], confirmed_only=True)
                if fact_records:
                    facts = fact_records[0]["facts"]

            matches.append({
                "bullet_index": idx,
                "bullet_text": bullet,
                **match_result,
                "has_facts": facts is not None,
                "facts": facts
            })

        return {
            "bullets": bullets,
            "matches": matches
        }

    except Exception as e:
        log.exception(f"Error matching bullets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply/generate_with_facts", response_model=BulletGenerationResponse)
async def generate_resume_with_facts(
    request: BulletGenerationRequest
):
    """
    Generate optimized resume using stored facts for matched bullets.

    Args:
        request: BulletGenerationRequest with user_id, job_description, bullets

    Returns:
        BulletGenerationResponse with enhanced bullets
    """
    try:
        # For each bullet, try to find stored facts
        enhanced_bullets = []
        with_facts = []
        without_facts = []

        for idx, bullet in enumerate(request.bullets):
            # Try to match bullet
            embedding = embed(bullet)
            match_result = match_bullet_with_confidence_optimized(
                request.user_id,
                bullet,
                embedding
            )

            # Get facts if matched
            facts = None
            if match_result["bullet_id"]:
                fact_records = get_bullet_facts(match_result["bullet_id"], confirmed_only=True)
                if fact_records:
                    facts = fact_records[0]["facts"]

            if facts:
                # Generate with facts
                enhanced = generate_bullet_with_facts(
                    bullet,
                    request.job_description,
                    facts
                )
                enhanced_bullets.append(enhanced)
                with_facts.append(idx)
                log.info(f"Generated bullet {idx} with stored facts")
            else:
                # Fallback to original bullet (or could use basic rewrite)
                enhanced_bullets.append(bullet)
                without_facts.append(idx)
                log.info(f"Bullet {idx} has no stored facts, using original")

        return BulletGenerationResponse(
            enhanced_bullets=enhanced_bullets,
            bullets_with_facts=with_facts,
            bullets_without_facts=without_facts
        )

    except Exception as e:
        log.exception(f"Error generating with facts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# ADD CONTEXT ENDPOINTS (Conversational AI)
# =====================================================================

class AddContextStartRequest(BaseModel):
    user_id: str
    bullet_text: str
    bullet_id: Optional[str] = None  # If adding to existing bullet
    job_description: Optional[str] = None  # Optional: helps generate better questions


class AddContextStartResponse(BaseModel):
    session_id: str
    bullet_id: str
    bullet_text: str
    questions: List[Dict[str, str]]  # List of {"question": str, "type": str, "id": str}
    message: str


class AddContextAnswerRequest(BaseModel):
    session_id: str
    answers: List[Dict[str, str]]  # [{"qa_id": str, "answer": str}]


class AddContextAnswerResponse(BaseModel):
    status: str  # "continue" | "complete"
    next_questions: Optional[List[Dict[str, str]]] = None
    extracted_facts: Optional[Dict] = None
    fact_id: Optional[str] = None
    message: str


@router.post("/context/start", response_model=AddContextStartResponse)
async def start_add_context(request: AddContextStartRequest):
    """
    Start a conversational context-gathering session for a bullet.

    User clicks "Add Context" on frontend → This endpoint is called.

    Flow:
    1. Creates a Q&A session for the bullet
    2. Generates initial questions using AI
    3. Returns questions for user to answer

    Args:
        user_id: User identifier
        bullet_text: The bullet text to add context for
        bullet_id: Optional existing bullet ID (if adding to existing)
        job_description: Optional JD to help generate relevant questions

    Returns:
        Session ID, bullet ID, and initial questions
    """
    try:
        user_id = request.user_id
        bullet_text = request.bullet_text

        # Create or get bullet
        if request.bullet_id:
            bullet_id = request.bullet_id
            log.info(f"Adding context to existing bullet: {bullet_id}")
        else:
            # Create new bullet
            embedding = embed(bullet_text)
            bullet_id = store_user_bullet(user_id, bullet_text, embedding)
            if not bullet_id:
                raise HTTPException(status_code=500, detail="Failed to store bullet")
            log.info(f"Created new bullet for context: {bullet_id}")

        # Create Q&A session
        session_id = create_qa_session(
            user_id,
            request.job_description or "",
            [bullet_text]
        )

        if not session_id:
            raise HTTPException(status_code=500, detail="Failed to create session")

        # Get existing context (if any) to avoid duplicate questions
        from db_utils import get_user_context
        existing_context = get_user_context(user_id)

        # Generate initial questions
        questions = generate_followup_questions(
            [bullet_text],
            request.job_description or "",
            existing_context,
            max_questions=5  # Start with 5 questions
        )

        # Store questions in database
        stored_questions = []
        for q in questions:
            qa_id = store_qa_pair(
                session_id,
                q["question"],
                None,  # No answer yet
                q.get("type"),
                0  # bullet_index = 0 (single bullet)
            )
            stored_questions.append({
                "question": q["question"],
                "type": q.get("type", "general"),
                "id": qa_id
            })

        return AddContextStartResponse(
            session_id=session_id,
            bullet_id=bullet_id,
            bullet_text=bullet_text,
            questions=stored_questions,
            message=f"Generated {len(stored_questions)} questions. Answer as many as you'd like - you can skip any."
        )

    except Exception as e:
        log.exception(f"Error starting context session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/answer", response_model=AddContextAnswerResponse)
async def submit_context_answers(request: AddContextAnswerRequest):
    """
    Submit answers to context questions. AI automatically decides if more questions needed.

    This is called when user submits answers in the conversational UI.

    Flow:
    1. Store user's answers
    2. LLM evaluates if enough context gathered (using should_ask_more_questions)
    3. If YES (enough): Extract facts and return them
    4. If NO (need more): Generate more questions and return them

    Args:
        session_id: The Q&A session ID
        answers: List of {"qa_id": str, "answer": str}

    Returns:
        Either:
        - status="continue" with next_questions
        - status="complete" with extracted_facts
    """
    try:
        session_id = request.session_id

        # Store answers
        for ans in request.answers:
            if ans.get("answer") and ans.get("answer").strip():
                from db_utils import update_qa_answer
                update_qa_answer(ans["qa_id"], ans["answer"])

        # Get session info
        from db_utils import get_qa_session
        session = get_qa_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        bullets = session.get("bullets", [])
        job_description = session.get("job_description", "")

        # Get all answered Q&A
        answered_qa = get_answered_qa_pairs(session_id)

        if not answered_qa:
            return AddContextAnswerResponse(
                status="continue",
                next_questions=[],
                message="No answers provided. Please answer at least one question."
            )

        # Ask LLM: Do we have enough context?
        need_more, reason = should_ask_more_questions(
            answered_qa,
            bullets,
            job_description
        )

        if not need_more:
            # COMPLETE: Extract facts
            log.info(f"Context gathering complete for session {session_id}: {reason}")

            bullet_text = bullets[0] if bullets else ""

            # Extract facts
            facts = extract_facts_from_qa(bullet_text, answered_qa)

            # Get bullet_id from session or answers
            bullet_id = session.get("bullet_id")
            if not bullet_id:
                # Try to find it from user_id and bullet_text
                from db_utils import check_exact_match
                user_id = session.get("user_id")
                bullet_id = check_exact_match(user_id, bullet_text)

            # Store facts (unconfirmed - user will confirm on frontend)
            fact_id = None
            if bullet_id:
                fact_id = store_bullet_facts(
                    bullet_id,
                    facts,
                    qa_session_id=session_id,
                    confirmed=False
                )

            # Store to user context for future
            from db_utils import store_user_context
            for qa in answered_qa:
                store_user_context(session.get("user_id"), qa["question"], qa["answer"])

            return AddContextAnswerResponse(
                status="complete",
                extracted_facts=facts,
                fact_id=fact_id,
                message=f"Great! I've gathered enough context. Review the extracted facts below."
            )

        else:
            # CONTINUE: Generate more questions
            log.info(f"Generating more questions for session {session_id}: {reason}")

            # Generate follow-up questions
            more_questions = generate_followup_questions(
                bullets,
                job_description,
                answered_qa,
                max_questions=3  # Just 3 more questions
            )

            # Store new questions
            stored_questions = []
            for q in more_questions:
                qa_id = store_qa_pair(
                    session_id,
                    q["question"],
                    None,
                    q.get("type"),
                    0
                )
                stored_questions.append({
                    "question": q["question"],
                    "type": q.get("type", "general"),
                    "id": qa_id
                })

            return AddContextAnswerResponse(
                status="continue",
                next_questions=stored_questions,
                message=f"Thanks! Just a few more questions to get the full picture. ({len(stored_questions)} questions)"
            )

    except Exception as e:
        log.exception(f"Error submitting context answers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/context/confirm_facts")
async def confirm_context_facts(
    fact_id: str = Form(...),
    edited_facts: Optional[str] = Form(None)  # JSON string if user edited
):
    """
    User confirms/edits the extracted facts.

    Called after user reviews facts in the UI.

    Args:
        fact_id: The fact ID from extract step
        edited_facts: Optional JSON string if user edited the facts

    Returns:
        Confirmation message
    """
    try:
        # If user edited, update first
        if edited_facts:
            import json
            facts = json.loads(edited_facts)
            success = update_bullet_facts(fact_id, facts)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update facts")

        # Confirm facts
        confirmed = confirm_bullet_facts(fact_id)
        if not confirmed:
            raise HTTPException(status_code=500, detail="Failed to confirm facts")

        return {
            "status": "success",
            "message": "Facts confirmed! These will be used for future resumes.",
            "fact_id": fact_id
        }

    except Exception as e:
        log.exception(f"Error confirming facts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Example integration into app.py:
# from api_endpoints_new import router as v2_router
# app.include_router(v2_router)
