"""
Optimized database utilities using PostgreSQL RPC functions for vector similarity.

This module provides drop-in replacements for functions in db_utils.py that use
database-side vector operations for better performance.

To use these optimized functions, simply replace the import:
    from db_utils_optimized import find_similar_bullets
"""

from typing import Dict, List, Any
from config import supabase, log


def find_similar_bullets_rpc(user_id: str, embedding: List[float],
                             threshold: float = 0.85, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find bullets similar to the given embedding using database-side RPC function.

    This is significantly faster than the Python implementation in db_utils.py
    because it performs the similarity calculation directly in PostgreSQL.

    Args:
        user_id: User identifier
        embedding: Vector embedding of the bullet
        threshold: Minimum similarity score (0.0-1.0, default 0.85)
        limit: Maximum number of results to return

    Returns:
        List of matching bullets with similarity scores, ordered by score DESC
        Each dict contains: bullet_id, bullet_text, similarity_score
    """
    if not supabase:
        log.warning("Supabase not configured. Cannot search similar bullets.")
        return []

    try:
        # Call the PostgreSQL function via Supabase RPC
        result = supabase.rpc(
            'find_similar_bullets',
            {
                'p_user_id': user_id,
                'p_embedding': embedding,
                'p_threshold': threshold,
                'p_limit': limit
            }
        ).execute()

        if not result.data:
            return []

        # Convert to expected format
        matches = []
        for row in result.data:
            matches.append({
                "id": row["bullet_id"],
                "bullet_text": row["bullet_text"],
                "similarity_score": row["similarity_score"]
            })

        log.info(f"Found {len(matches)} similar bullets for user {user_id}")
        return matches

    except Exception as e:
        log.exception(f"Error finding similar bullets via RPC: {e}")
        # Fallback to Python implementation
        log.warning("Falling back to Python similarity calculation")
        from db_utils import find_similar_bullets as python_fallback
        return python_fallback(user_id, "", embedding, threshold, limit)


def match_bullet_with_confidence_optimized(user_id: str, bullet_text: str,
                                          embedding: List[float]) -> Dict[str, Any]:
    """
    Optimized version of match_bullet_with_confidence using RPC function.

    Same interface as db_utils.match_bullet_with_confidence but uses database-side
    vector operations for better performance.

    Args:
        user_id: User identifier
        bullet_text: The bullet text to match
        embedding: Vector embedding of the bullet

    Returns:
        Dict with match information (see db_utils.match_bullet_with_confidence)
    """
    from db_utils import check_exact_match, get_user_bullet

    # First check for exact match (fast lookup)
    exact_match_id = check_exact_match(user_id, bullet_text)
    if exact_match_id:
        bullet_data = get_user_bullet(exact_match_id)
        return {
            "match_type": "exact",
            "bullet_id": exact_match_id,
            "similarity_score": 1.0,
            "existing_bullet_text": bullet_data.get("bullet_text") if bullet_data else None
        }

    # Use optimized RPC-based similarity search
    similar_bullets = find_similar_bullets_rpc(user_id, embedding, threshold=0.85, limit=1)

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


# Example usage:
if __name__ == "__main__":
    # This demonstrates how to use the optimized functions
    from llm_utils import embed

    # Example: Match a bullet
    user_id = "user123"
    bullet_text = "Led team of 5 engineers to build microservices platform"
    embedding = embed(bullet_text)

    result = match_bullet_with_confidence_optimized(user_id, bullet_text, embedding)
    print(f"Match result: {result}")
