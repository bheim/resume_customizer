"""Database utilities for Q&A session management with Supabase."""

import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime
from config import supabase, log


def hash_question(question: str) -> str:
    """Generate a hash for a question to avoid duplicate storage."""
    return hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()


def create_qa_session(user_id: Optional[str], job_description: str, bullets: List[str]) -> Optional[str]:
    """
    Create a new Q&A session in the database.

    Args:
        user_id: Optional user identifier
        job_description: The job description text
        bullets: List of original resume bullet points

    Returns:
        Session ID if successful, None otherwise
    """
    if not supabase:
        log.warning("Supabase not configured. Cannot create Q&A session.")
        return None

    try:
        data = {
            "user_id": user_id or "anonymous",
            "job_description": job_description,
            "bullets": bullets,
            "status": "active"
        }

        result = supabase.table("qa_sessions").insert(data).execute()

        if result.data and len(result.data) > 0:
            session_id = result.data[0]["id"]
            log.info(f"Created Q&A session: {session_id}")
            return session_id
        else:
            log.error("Failed to create Q&A session: no data returned")
            return None

    except Exception as e:
        log.exception(f"Error creating Q&A session: {e}")
        return None


def get_qa_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a Q&A session by ID.

    Args:
        session_id: The session ID to retrieve

    Returns:
        Session data if found, None otherwise
    """
    if not supabase:
        return None

    try:
        result = supabase.table("qa_sessions").select("*").eq("id", session_id).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        log.exception(f"Error retrieving Q&A session: {e}")
        return None


def store_qa_pair(session_id: str, question: str, answer: Optional[str] = None,
                  question_type: Optional[str] = None) -> Optional[str]:
    """
    Store a Q&A pair in the database.

    Args:
        session_id: The session ID this Q&A belongs to
        question: The question text
        answer: The answer text (can be None if not yet answered)
        question_type: Type/category of the question

    Returns:
        Q&A pair ID if successful, None otherwise
    """
    if not supabase:
        return None

    try:
        data = {
            "session_id": session_id,
            "question": question,
            "answer": answer,
            "question_type": question_type,
            "answered_at": datetime.utcnow().isoformat() if answer else None
        }

        result = supabase.table("qa_pairs").insert(data).execute()

        if result.data and len(result.data) > 0:
            qa_id = result.data[0]["id"]
            log.info(f"Stored Q&A pair: {qa_id}")
            return qa_id
        return None

    except Exception as e:
        log.exception(f"Error storing Q&A pair: {e}")
        return None


def update_qa_answer(qa_id: str, answer: str) -> bool:
    """
    Update the answer for a Q&A pair.

    Args:
        qa_id: The Q&A pair ID
        answer: The answer text

    Returns:
        True if successful, False otherwise
    """
    if not supabase:
        return False

    try:
        data = {
            "answer": answer,
            "answered_at": datetime.utcnow().isoformat()
        }

        result = supabase.table("qa_pairs").update(data).eq("id", qa_id).execute()

        return bool(result.data)

    except Exception as e:
        log.exception(f"Error updating Q&A answer: {e}")
        return False


def get_session_qa_pairs(session_id: str) -> List[Dict[str, Any]]:
    """
    Get all Q&A pairs for a session.

    Args:
        session_id: The session ID

    Returns:
        List of Q&A pairs
    """
    if not supabase:
        return []

    try:
        result = supabase.table("qa_pairs").select("*").eq("session_id", session_id).order("asked_at").execute()

        return result.data if result.data else []

    except Exception as e:
        log.exception(f"Error retrieving Q&A pairs: {e}")
        return []


def get_user_context(user_id: str) -> List[Dict[str, Any]]:
    """
    Get all stored Q&A context for a user to avoid repeat questions.

    Args:
        user_id: The user ID

    Returns:
        List of stored Q&A pairs for this user
    """
    if not supabase or not user_id or user_id == "anonymous":
        return []

    try:
        result = supabase.table("user_context").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()

        return result.data if result.data else []

    except Exception as e:
        log.exception(f"Error retrieving user context: {e}")
        return []


def store_user_context(user_id: str, question: str, answer: str) -> bool:
    """
    Store a Q&A pair in the user's context to avoid repeat questions.

    Args:
        user_id: The user ID
        question: The question text
        answer: The answer text

    Returns:
        True if successful, False otherwise
    """
    if not supabase or not user_id or user_id == "anonymous":
        return False

    try:
        data = {
            "user_id": user_id,
            "question_hash": hash_question(question),
            "question": question,
            "answer": answer
        }

        # Use upsert to handle duplicates
        result = supabase.table("user_context").upsert(data, on_conflict="user_id,question_hash").execute()

        return bool(result.data)

    except Exception as e:
        log.exception(f"Error storing user context: {e}")
        return False


def update_session_status(session_id: str, status: str) -> bool:
    """
    Update the status of a Q&A session.

    Args:
        session_id: The session ID
        status: New status (active, completed, abandoned)

    Returns:
        True if successful, False otherwise
    """
    if not supabase:
        return False

    try:
        result = supabase.table("qa_sessions").update({"status": status}).eq("id", session_id).execute()

        return bool(result.data)

    except Exception as e:
        log.exception(f"Error updating session status: {e}")
        return False


def get_answered_qa_pairs(session_id: str) -> List[Dict[str, str]]:
    """
    Get all answered Q&A pairs for a session (for context in rewriting).

    Args:
        session_id: The session ID

    Returns:
        List of dicts with 'question' and 'answer' keys
    """
    if not supabase:
        return []

    try:
        result = (supabase.table("qa_pairs")
                 .select("question, answer")
                 .eq("session_id", session_id)
                 .not_.is_("answer", "null")
                 .order("asked_at")
                 .execute())

        return result.data if result.data else []

    except Exception as e:
        log.exception(f"Error retrieving answered Q&A pairs: {e}")
        return []
