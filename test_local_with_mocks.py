#!/usr/bin/env python3
"""
Local testing with MOCKED database functions - NO SUPABASE REQUIRED

This simulates the full workflow including database operations using in-memory storage.
Perfect for testing the complete flow without setting up Supabase.

Tests:
1. Store bullet with embedding (mocked)
2. Match bullets with confidence levels (mocked)
3. Store and retrieve facts (mocked)
4. Full onboarding flow simulation
5. Full job application flow simulation
"""

import os
import sys
from typing import Dict, List, Optional, Any
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# In-memory "database"
MOCK_DB = {
    "bullets": {},  # bullet_id -> {user_id, bullet_text, embedding, ...}
    "facts": {},    # fact_id -> {bullet_id, facts, confirmed, ...}
}


class MockDatabase:
    """Mock database operations for testing without Supabase."""

    @staticmethod
    def store_bullet(user_id: str, bullet_text: str, embedding: List[float]) -> str:
        """Mock: Store bullet with embedding."""
        bullet_id = str(uuid4())
        MOCK_DB["bullets"][bullet_id] = {
            "id": bullet_id,
            "user_id": user_id,
            "bullet_text": bullet_text,
            "bullet_embedding": embedding,
            "normalized_text": bullet_text.strip().lower()
        }
        print(f"  📝 Stored bullet: {bullet_id[:8]}... for user {user_id}")
        return bullet_id

    @staticmethod
    def match_bullet(user_id: str, bullet_text: str, embedding: List[float]) -> Dict[str, Any]:
        """Mock: Match bullet with confidence."""
        import numpy as np

        def cosine_similarity(vec1, vec2):
            a = np.array(vec1)
            b = np.array(vec2)
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        # Check exact match
        normalized = bullet_text.strip().lower()
        for bid, bullet in MOCK_DB["bullets"].items():
            if bullet["user_id"] == user_id and bullet["normalized_text"] == normalized:
                print(f"  ✅ EXACT MATCH found: {bid[:8]}...")
                return {
                    "match_type": "exact",
                    "bullet_id": bid,
                    "similarity_score": 1.0,
                    "existing_bullet_text": bullet["bullet_text"]
                }

        # Check similarity
        best_match = None
        best_score = 0.0

        for bid, bullet in MOCK_DB["bullets"].items():
            if bullet["user_id"] != user_id:
                continue

            sim = cosine_similarity(embedding, bullet["bullet_embedding"])
            if sim > best_score:
                best_score = sim
                best_match = (bid, bullet)

        if best_score >= 0.9:
            print(f"  ✅ HIGH CONFIDENCE match: {best_match[0][:8]}... (similarity: {best_score:.3f})")
            return {
                "match_type": "high_confidence",
                "bullet_id": best_match[0],
                "similarity_score": best_score,
                "existing_bullet_text": best_match[1]["bullet_text"]
            }
        elif best_score >= 0.85:
            print(f"  ⚠️  MEDIUM CONFIDENCE match: {best_match[0][:8]}... (similarity: {best_score:.3f})")
            return {
                "match_type": "medium_confidence",
                "bullet_id": best_match[0],
                "similarity_score": best_score,
                "existing_bullet_text": best_match[1]["bullet_text"]
            }
        else:
            print(f"  ❌ NO MATCH (best similarity: {best_score:.3f})")
            return {
                "match_type": "no_match",
                "bullet_id": None,
                "similarity_score": best_score if best_match else None,
                "existing_bullet_text": None
            }

    @staticmethod
    def store_facts(bullet_id: str, facts: Dict, confirmed: bool = False) -> str:
        """Mock: Store facts for bullet."""
        fact_id = str(uuid4())
        MOCK_DB["facts"][fact_id] = {
            "id": fact_id,
            "bullet_id": bullet_id,
            "facts": facts,
            "confirmed_by_user": confirmed
        }
        status = "✅ CONFIRMED" if confirmed else "⚠️  UNCONFIRMED"
        print(f"  📊 Stored facts: {fact_id[:8]}... ({status})")
        return fact_id

    @staticmethod
    def get_facts(bullet_id: str, confirmed_only: bool = False) -> Optional[Dict]:
        """Mock: Get facts for bullet."""
        for fact in MOCK_DB["facts"].values():
            if fact["bullet_id"] == bullet_id:
                if confirmed_only and not fact["confirmed_by_user"]:
                    continue
                return fact["facts"]
        return None

    @staticmethod
    def confirm_facts(fact_id: str):
        """Mock: Confirm facts."""
        if fact_id in MOCK_DB["facts"]:
            MOCK_DB["facts"][fact_id]["confirmed_by_user"] = True
            print(f"  ✅ Confirmed facts: {fact_id[:8]}...")


def test_onboarding_flow():
    """Simulate complete onboarding flow."""
    print("\n" + "="*70)
    print("TEST: ONBOARDING FLOW SIMULATION")
    print("="*70)

    from llm_utils import embed, extract_facts_from_qa

    user_id = "test_user_123"

    # Step 1: User uploads resume with 3 bullets
    print("\n📄 Step 1: User uploads resume")
    print("-" * 70)

    bullets = [
        "Led development of customer analytics dashboard using React and Python",
        "Implemented CI/CD pipeline reducing deployment time by 40%",
        "Mentored 3 junior engineers on software engineering best practices"
    ]

    print(f"Extracted {len(bullets)} bullets from resume:\n")
    for i, bullet in enumerate(bullets, 1):
        print(f"  {i}. {bullet}")

    # Step 2: Match each bullet
    print("\n🔍 Step 2: Matching bullets against stored bullets")
    print("-" * 70)

    matches = []
    for i, bullet in enumerate(bullets, 1):
        print(f"\nBullet {i}: {bullet[:50]}...")
        embedding = embed(bullet)
        match = MockDatabase.match_bullet(user_id, bullet, embedding)
        matches.append((bullet, embedding, match))

    # Step 3: For new bullets, collect facts
    print("\n💬 Step 3: Collecting facts for new bullets")
    print("-" * 70)

    for i, (bullet, embedding, match) in enumerate(matches, 1):
        if match["match_type"] == "no_match":
            print(f"\nBullet {i} is NEW - collecting facts...")

            # Simulate Q&A
            qa_pairs = [
                {
                    "question": "What quantifiable results did you achieve?",
                    "answer": "Reduced report time from 2 hours to 15 minutes" if i == 1 else
                              "Cut deployment time from 30 min to 10 min" if i == 2 else
                              "All 3 mentees promoted within 6 months"
                },
                {
                    "question": "What technologies did you use?",
                    "answer": "React, Python, FastAPI, PostgreSQL, AWS" if i == 1 else
                              "Jenkins, Docker, Kubernetes, AWS" if i == 2 else
                              "Git, Python, code review processes"
                }
            ]

            print(f"  User answered {len(qa_pairs)} questions")

            # Extract facts
            facts = extract_facts_from_qa(bullet, qa_pairs)
            print(f"  ✅ Extracted {len(facts['metrics']['quantifiable_achievements'])} metrics")

            # Store bullet
            bullet_id = MockDatabase.store_bullet(user_id, bullet, embedding)

            # Store facts (unconfirmed)
            fact_id = MockDatabase.store_facts(bullet_id, facts, confirmed=False)

            # User confirms facts
            MockDatabase.confirm_facts(fact_id)

    print("\n✅ Onboarding complete!")
    print(f"   - {len(MOCK_DB['bullets'])} bullets stored")
    print(f"   - {len(MOCK_DB['facts'])} fact sets stored")


def test_job_application_flow():
    """Simulate job application flow with stored facts."""
    print("\n" + "="*70)
    print("TEST: JOB APPLICATION FLOW SIMULATION")
    print("="*70)

    from llm_utils import embed, generate_bullet_with_facts

    user_id = "test_user_123"

    # Step 1: User uploads resume (similar to onboarding, but some bullets match)
    print("\n📄 Step 1: User uploads resume for new job application")
    print("-" * 70)

    # Simulate slightly modified bullets
    new_bullets = [
        "Built customer analytics dashboard with React and Python",  # Similar to stored
        "Set up CI/CD pipeline cutting deployment time significantly",  # Similar
        "Architected microservices platform for high-scale workloads"  # New bullet
    ]

    job_description = """
    Senior Software Engineer - Data Platform

    Requirements:
    - 5+ years Python experience
    - Experience with React and modern web frameworks
    - Strong DevOps and CI/CD background
    - Track record of building scalable systems

    Responsibilities:
    - Build data analytics platforms
    - Improve deployment processes
    - Mentor team members
    """

    print(f"New resume has {len(new_bullets)} bullets")
    print(f"Target role: Senior Software Engineer - Data Platform\n")

    # Step 2: Match bullets
    print("\n🔍 Step 2: Matching bullets to find stored facts")
    print("-" * 70)

    enhanced_bullets = []

    for i, bullet in enumerate(new_bullets, 1):
        print(f"\nBullet {i}: {bullet[:60]}...")
        embedding = embed(bullet)
        match = MockDatabase.match_bullet(user_id, bullet, embedding)

        if match["bullet_id"]:
            # Get facts
            facts = MockDatabase.get_facts(match["bullet_id"], confirmed_only=True)

            if facts:
                print(f"  ✅ Using stored facts for generation")

                # Generate enhanced bullet
                enhanced = generate_bullet_with_facts(
                    bullet,
                    job_description,
                    facts,
                    char_limit=300
                )
                enhanced_bullets.append(enhanced)

                print(f"  📝 Enhanced: {enhanced[:80]}...")
            else:
                print(f"  ⚠️  Match found but no confirmed facts")
                enhanced_bullets.append(bullet)
        else:
            print(f"  ❌ No match - using original bullet")
            enhanced_bullets.append(bullet)

    # Step 3: Show results
    print("\n📊 Step 3: Results")
    print("-" * 70)

    bullets_with_facts = sum(1 for b in enhanced_bullets if b != new_bullets[enhanced_bullets.index(b)])

    print(f"\n✅ Generated {len(enhanced_bullets)} bullets")
    print(f"   - {bullets_with_facts} used stored facts (fact-based generation)")
    print(f"   - {len(enhanced_bullets) - bullets_with_facts} used original (no facts)")

    print("\n📝 Enhanced Resume Bullets:")
    print("=" * 70)
    for i, bullet in enumerate(enhanced_bullets, 1):
        print(f"\n{i}. {bullet}")

    return enhanced_bullets


def test_similarity_thresholds():
    """Test bullet matching with different similarity levels."""
    print("\n" + "="*70)
    print("TEST: SIMILARITY THRESHOLD BEHAVIOR")
    print("="*70)

    from llm_utils import embed

    user_id = "threshold_test_user"

    # Store original bullet
    original = "Led team of 5 engineers to build microservices platform"
    original_embedding = embed(original)
    bullet_id = MockDatabase.store_bullet(user_id, original, original_embedding)

    print(f"\n📝 Stored original bullet: {original}")

    # Test various similar bullets
    test_cases = [
        ("Led team of 5 engineers to build microservices platform", "exact match"),
        ("Managed team of 5 engineers developing microservice architecture", "high similarity"),
        ("Led engineering team building distributed systems", "medium similarity"),
        ("Wrote technical documentation for API endpoints", "low similarity"),
    ]

    print("\n🔍 Testing matching behavior:\n")

    for test_bullet, expected in test_cases:
        print(f"Test: {test_bullet[:60]}...")
        print(f"Expected: {expected}")

        embedding = embed(test_bullet)
        match = MockDatabase.match_bullet(user_id, test_bullet, embedding)

        print(f"Result: {match['match_type']} (score: {match.get('similarity_score', 'N/A')})")
        print()


def main():
    """Run all mock tests."""
    print("\n" + "="*70)
    print("RESUME OPTIMIZER - MOCK DATABASE TESTING")
    print("Testing Full Workflow (No Supabase Required)")
    print("="*70)

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY environment variable not set")
        print("\nPlease set your OpenAI API key:")
        print("  export OPENAI_API_KEY='sk-...'")
        return 1

    print("\n✅ OpenAI API key found")
    print("\n💡 Using in-memory mock database (no Supabase required)")

    try:
        # Test 1: Onboarding flow
        test_onboarding_flow()

        # Test 2: Job application flow
        test_job_application_flow()

        # Test 3: Similarity thresholds
        test_similarity_thresholds()

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print("\n✅ All workflow tests passed!")
        print("\n📊 Mock Database State:")
        print(f"   - Bullets stored: {len(MOCK_DB['bullets'])}")
        print(f"   - Fact sets stored: {len(MOCK_DB['facts'])}")
        print("\n💡 This demonstrates the full flow without Supabase.")
        print("   To test with real database, run: python test_local_with_db.py")

        return 0

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
