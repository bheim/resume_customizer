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
                  question_type: Optional[str] = None, bullet_index: Optional[int] = None) -> Optional[str]:
    """
    Store a Q&A pair in the database.

    Args:
        session_id: The session ID this Q&A belongs to
        question: The question text
        answer: The answer text (can be None if not yet answered)
        question_type: Type/category of the question
        bullet_index: Index of the bullet this question is about (optional)

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
            "bullet_index": bullet_index,
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
        log.warning("Supabase not configured, cannot update answer")
        return False

    try:
        # First check if the qa_pair exists
        check_result = supabase.table("qa_pairs").select("id").eq("id", qa_id).execute()
        if not check_result.data or len(check_result.data) == 0:
            log.error(f"QA pair {qa_id} does not exist in database")
            return False

        data = {
            "answer": answer,
            "answered_at": datetime.utcnow().isoformat()
        }

        result = supabase.table("qa_pairs").update(data).eq("id", qa_id).execute()

        if result.data and len(result.data) > 0:
            log.info(f"Successfully updated answer for qa_id={qa_id}")
            return True
        else:
            log.error(f"Update returned no data for qa_id={qa_id}. RLS may be blocking the update.")
            return False

    except Exception as e:
        log.exception(f"Error updating Q&A answer for qa_id={qa_id}: {e}")
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


# =====================================================================
# Bullet Management Functions (for persistent bullet storage)
# =====================================================================

def store_user_bullet(user_id: str, bullet_text: str, embedding: List[float],
                     source_resume: Optional[str] = None) -> Optional[str]:
    """
    Store a bullet with its embedding in the database.
    If bullet already exists (same user + normalized text), update it instead of creating duplicate.

    Args:
        user_id: User identifier
        bullet_text: The original bullet text
        embedding: Vector embedding of the bullet (1536 dimensions for text-embedding-3-small)
        source_resume: Optional filename of the source resume

    Returns:
        Bullet ID if successful, None otherwise
    """
    if not supabase:
        log.warning("Supabase not configured. Cannot store bullet.")
        return None

    try:
        # Check if bullet already exists for this user
        existing_id = check_exact_match(user_id, bullet_text)

        if existing_id:
            # Update existing bullet
            log.info(f"Bullet already exists: {existing_id}, updating embedding")
            update_data = {
                "bullet_embedding": embedding,
                "updated_at": "now()"
            }
            if source_resume:
                update_data["source_resume_name"] = source_resume

            result = supabase.table("user_bullets").update(update_data).eq("id", existing_id).execute()

            if result.data and len(result.data) > 0:
                log.info(f"Updated existing bullet: {existing_id}")
                return existing_id
            else:
                log.warning(f"Update returned no data, returning existing ID anyway: {existing_id}")
                return existing_id
        else:
            # Create new bullet
            data = {
                "user_id": user_id,
                "bullet_text": bullet_text,
                "bullet_embedding": embedding,
                "source_resume_name": source_resume
            }

            result = supabase.table("user_bullets").insert(data).execute()

            if result.data and len(result.data) > 0:
                bullet_id = result.data[0]["id"]
                log.info(f"Stored new bullet: {bullet_id}")
                return bullet_id
            else:
                log.error("Failed to store bullet: no data returned")
                return None

    except Exception as e:
        log.exception(f"Error storing bullet: {e}")
        return None


def get_user_bullet(bullet_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a bullet by ID.

    Args:
        bullet_id: The bullet ID to retrieve

    Returns:
        Bullet data if found, None otherwise
    """
    if not supabase:
        return None

    try:
        result = supabase.table("user_bullets").select("*").eq("id", bullet_id).execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception as e:
        log.exception(f"Error retrieving bullet: {e}")
        return None


def check_exact_match(user_id: str, bullet_text: str) -> Optional[str]:
    """
    Check for exact text match in user's bullets (case-insensitive, whitespace-trimmed).

    Args:
        user_id: User identifier
        bullet_text: The bullet text to match

    Returns:
        Bullet ID if exact match found, None otherwise
    """
    if not supabase:
        return None

    try:
        normalized = bullet_text.strip().lower()
        result = (supabase.table("user_bullets")
                 .select("id")
                 .eq("user_id", user_id)
                 .eq("normalized_text", normalized)
                 .limit(1)
                 .execute())

        if result.data and len(result.data) > 0:
            bullet_id = result.data[0]["id"]
            log.info(f"Found exact match for bullet: {bullet_id}")
            return bullet_id
        return None

    except Exception as e:
        log.exception(f"Error checking exact match: {e}")
        return None


def find_similar_bullets(user_id: str, bullet_text: str, embedding: List[float],
                        threshold: float = 0.85, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find bullets similar to the given text using embedding similarity (cosine distance).

    Args:
        user_id: User identifier
        bullet_text: The bullet text to match
        embedding: Vector embedding of the bullet
        threshold: Minimum similarity score (0.0-1.0, default 0.85)
        limit: Maximum number of results to return

    Returns:
        List of matching bullets with similarity scores, ordered by score DESC
        Each dict contains: id, bullet_text, similarity_score
    """
    if not supabase:
        log.warning("Supabase not configured. Cannot search similar bullets.")
        return []

    try:
        # PostgreSQL with pgvector: <=> is cosine distance operator
        # Cosine similarity = 1 - cosine distance
        # We need to filter by user_id first, then calculate similarity

        # Using RPC function for better performance (we'll create this separately)
        # For now, use a direct query with distance calculation

        # Note: Supabase Python client may not support vector operations directly
        # We'll use execute() with raw SQL via rpc() or direct query

        # Option 1: Use postgrest RPC (requires creating a database function)
        # Option 2: Fetch all user bullets and calculate similarity in Python

        # For production, create a PostgreSQL function. For now, we'll use a workaround:
        # Fetch user's bullets and calculate cosine similarity in Python

        result = (supabase.table("user_bullets")
                 .select("id, bullet_text, bullet_embedding")
                 .eq("user_id", user_id)
                 .execute())

        if not result.data:
            return []

        # Calculate cosine similarity in Python
        import numpy as np

        def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
            """Calculate cosine similarity between two vectors."""
            if not vec1 or not vec2:
                return 0.0
            a = np.array(vec1)
            b = np.array(vec2)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

        matches = []
        for bullet in result.data:
            if bullet.get("bullet_embedding"):
                similarity = cosine_similarity(embedding, bullet["bullet_embedding"])
                if similarity >= threshold:
                    matches.append({
                        "id": bullet["id"],
                        "bullet_text": bullet["bullet_text"],
                        "similarity_score": similarity
                    })

        # Sort by similarity descending
        matches.sort(key=lambda x: x["similarity_score"], reverse=True)

        return matches[:limit]

    except Exception as e:
        log.exception(f"Error finding similar bullets: {e}")
        return []


def match_bullet_with_confidence(user_id: str, bullet_text: str, embedding: List[float]) -> Dict[str, Any]:
    """
    Match a bullet and return confidence level based on similarity.

    Confidence levels:
    - exact: Normalized text matches exactly
    - high_confidence: Similarity >= 0.9
    - medium_confidence: Similarity 0.85-0.9
    - no_match: Similarity < 0.85

    Args:
        user_id: User identifier
        bullet_text: The bullet text to match
        embedding: Vector embedding of the bullet

    Returns:
        Dict with match information:
        {
            "match_type": "exact" | "high_confidence" | "medium_confidence" | "no_match",
            "bullet_id": str | None,
            "similarity_score": float | None,
            "existing_bullet_text": str | None
        }
    """
    # First check for exact match
    exact_match_id = check_exact_match(user_id, bullet_text)
    if exact_match_id:
        bullet_data = get_user_bullet(exact_match_id)
        return {
            "match_type": "exact",
            "bullet_id": exact_match_id,
            "similarity_score": 1.0,
            "existing_bullet_text": bullet_data.get("bullet_text") if bullet_data else None
        }

    # Check for similar matches
    similar_bullets = find_similar_bullets(user_id, bullet_text, embedding, threshold=0.85, limit=1)

    if not similar_bullets:
        return {
            "match_type": "no_match",
            "bullet_id": None,
            "similarity_score": None,
            "existing_bullet_text": None
        }

    best_match = similar_bullets[0]
    similarity = best_match["similarity_score"]

    if similarity >= 0.9:
        match_type = "high_confidence"
    else:  # 0.85 <= similarity < 0.9
        match_type = "medium_confidence"

    return {
        "match_type": match_type,
        "bullet_id": best_match["id"],
        "similarity_score": similarity,
        "existing_bullet_text": best_match["bullet_text"]
    }


def update_bullet_embedding(bullet_id: str, embedding: List[float]) -> bool:
    """
    Update the embedding for a bullet (e.g., if text was modified).

    Args:
        bullet_id: The bullet ID
        embedding: New vector embedding

    Returns:
        True if successful, False otherwise
    """
    if not supabase:
        return False

    try:
        result = (supabase.table("user_bullets")
                 .update({"bullet_embedding": embedding})
                 .eq("id", bullet_id)
                 .execute())

        return bool(result.data)

    except Exception as e:
        log.exception(f"Error updating bullet embedding: {e}")
        return False


# =====================================================================
# Fact Management Functions
# =====================================================================

def store_bullet_facts(bullet_id: str, facts: Dict[str, Any],
                      qa_session_id: Optional[str] = None,
                      confirmed: bool = False) -> Optional[str]:
    """
    Store extracted facts for a bullet.
    If facts already exist for this bullet, update them instead of creating duplicates.

    Args:
        bullet_id: The bullet ID
        facts: Structured facts dictionary (following BulletFacts schema)
        qa_session_id: Optional Q&A session that generated these facts
        confirmed: Whether user has confirmed these facts

    Returns:
        Fact ID if successful, None otherwise
    """
    if not supabase:
        log.warning("Supabase not configured. Cannot store facts.")
        return None

    try:
        # Check if facts already exist for this bullet
        existing = supabase.table("bullet_facts").select("id").eq("bullet_id", bullet_id).order("created_at", desc=True).limit(1).execute()

        if existing.data and len(existing.data) > 0:
            # Update existing facts
            fact_id = existing.data[0]["id"]
            log.info(f"Updating existing facts for bullet {bullet_id}: {fact_id}")

            update_data = {
                "facts": facts,
                "qa_session_id": qa_session_id,
                "confirmed_by_user": confirmed,
                "updated_at": "now()"
            }

            result = supabase.table("bullet_facts").update(update_data).eq("id", fact_id).execute()

            if result.data and len(result.data) > 0:
                log.info(f"Updated facts for bullet {bullet_id}: {fact_id}")
                return fact_id
            else:
                log.warning(f"Update returned no data, returning existing ID: {fact_id}")
                return fact_id
        else:
            # Create new facts
            data = {
                "bullet_id": bullet_id,
                "facts": facts,
                "qa_session_id": qa_session_id,
                "confirmed_by_user": confirmed
            }

            result = supabase.table("bullet_facts").insert(data).execute()

            if result.data and len(result.data) > 0:
                fact_id = result.data[0]["id"]
                log.info(f"Stored new facts for bullet {bullet_id}: {fact_id}")
                return fact_id
            else:
                log.error("Failed to store facts: no data returned")
                return None

    except Exception as e:
        log.exception(f"Error storing facts: {e}")
        return None


def get_bullet_facts(bullet_id: str, confirmed_only: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieve facts for a bullet.

    Args:
        bullet_id: The bullet ID
        confirmed_only: If True, only return user-confirmed facts

    Returns:
        List of fact records (may have multiple fact versions)
    """
    if not supabase:
        return []

    try:
        query = supabase.table("bullet_facts").select("*").eq("bullet_id", bullet_id)

        if confirmed_only:
            query = query.eq("confirmed_by_user", True)

        result = query.order("created_at", desc=True).execute()

        return result.data if result.data else []

    except Exception as e:
        log.exception(f"Error retrieving bullet facts: {e}")
        return []


def confirm_bullet_facts(fact_id: str) -> bool:
    """
    Mark facts as user-confirmed.

    Args:
        fact_id: The fact ID

    Returns:
        True if successful, False otherwise
    """
    if not supabase:
        return False

    try:
        result = (supabase.table("bullet_facts")
                 .update({"confirmed_by_user": True})
                 .eq("id", fact_id)
                 .execute())

        if result.data:
            log.info(f"Confirmed facts: {fact_id}")
            return True
        return False

    except Exception as e:
        log.exception(f"Error confirming facts: {e}")
        return False


def update_bullet_facts(fact_id: str, facts: Dict[str, Any]) -> bool:
    """
    Update facts (e.g., after user edits).

    Args:
        fact_id: The fact ID
        facts: Updated facts dictionary

    Returns:
        True if successful, False otherwise
    """
    if not supabase:
        return False

    try:
        result = (supabase.table("bullet_facts")
                 .update({"facts": facts})
                 .eq("id", fact_id)
                 .execute())

        if result.data:
            log.info(f"Updated facts: {fact_id}")
            return True
        return False

    except Exception as e:
        log.exception(f"Error updating facts: {e}")
        return False
