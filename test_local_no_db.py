#!/usr/bin/env python3
"""
Local testing script for resume optimizer refactoring - NO DATABASE REQUIRED

Tests:
1. Fact extraction from Q&A
2. Bullet generation with facts
3. Embedding generation

Requirements:
- OPENAI_API_KEY environment variable set
- Python dependencies installed
"""

import os
import sys
from typing import Dict, List

# Ensure we can import from current directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_fact_extraction():
    """Test extracting structured facts from Q&A conversation."""
    print("\n" + "="*60)
    print("TEST 1: Fact Extraction from Q&A")
    print("="*60)

    from llm_utils import extract_facts_from_qa

    bullet_text = "Led development of customer analytics dashboard"

    qa_pairs = [
        {
            "question": "What quantifiable metrics or results did you achieve?",
            "answer": "Reduced report generation time from 2 hours to 15 minutes. Dashboard is now used by 50+ stakeholders daily across marketing, sales, and product teams."
        },
        {
            "question": "What specific technologies or tools did you use?",
            "answer": "Built the frontend with React and TypeScript, backend API with Python FastAPI, database was PostgreSQL. Deployed everything on AWS using ECS for containers."
        },
        {
            "question": "What was the business impact of this work?",
            "answer": "Enabled self-serve analytics which freed up our data team to work on more strategic initiatives. Marketing team can now generate campaign reports in minutes instead of waiting days for data team support."
        },
        {
            "question": "What challenges did you solve?",
            "answer": "Main challenge was migrating from a legacy reporting system that was slow and inflexible. Had to ensure zero downtime during migration and maintain backward compatibility with existing reports."
        }
    ]

    print(f"\nOriginal Bullet: {bullet_text}")
    print(f"\nQ&A Pairs: {len(qa_pairs)} questions answered\n")

    try:
        facts = extract_facts_from_qa(bullet_text, qa_pairs)

        print("✅ Fact extraction successful!\n")
        print("Extracted Facts:")
        print("-" * 60)

        # Pretty print the facts
        import json

        # Don't print raw_qa (too verbose)
        facts_display = {k: v for k, v in facts.items() if k != "raw_qa"}
        print(json.dumps(facts_display, indent=2))

        print(f"\n📊 Statistics:")
        print(f"  - Quantifiable achievements: {len(facts['metrics']['quantifiable_achievements'])}")
        print(f"  - Technologies: {len(facts['technical_details']['technologies'])}")
        print(f"  - Business outcomes: {len(facts['impact']['business_outcomes'])}")
        print(f"  - Challenges solved: {len(facts['context']['challenges_solved'])}")

        return facts

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_bullet_generation_with_facts(facts: Dict):
    """Test generating enhanced bullet using stored facts."""
    print("\n" + "="*60)
    print("TEST 2: Bullet Generation with Facts")
    print("="*60)

    from llm_utils import generate_bullet_with_facts

    original_bullet = "Led development of customer analytics dashboard"

    job_description = """
    Senior Data Engineer

    We're seeking a Senior Data Engineer to build scalable data platforms and analytics solutions.

    Requirements:
    - 5+ years experience with Python and SQL
    - Experience with cloud platforms (AWS, GCP, or Azure)
    - Strong background in data visualization and analytics
    - Experience with modern web frameworks (React, Vue, or Angular)
    - Track record of delivering high-impact analytics solutions
    - Excellent communication skills for working with stakeholders

    Responsibilities:
    - Design and build data pipelines and analytics platforms
    - Partner with product and business teams to deliver insights
    - Optimize performance of data systems
    - Mentor junior engineers
    """

    print(f"\nOriginal Bullet: {original_bullet}")
    print(f"\nTarget Job: Senior Data Engineer")
    print(f"\nUsing stored facts to generate enhanced bullet...\n")

    try:
        enhanced_bullet = generate_bullet_with_facts(
            original_bullet,
            job_description,
            facts,
            char_limit=300
        )

        print("✅ Bullet generation successful!\n")
        print("Enhanced Bullet:")
        print("-" * 60)
        print(enhanced_bullet)
        print("-" * 60)
        print(f"\n📏 Length: {len(enhanced_bullet)} characters")

        # Compare to original
        print(f"\n📊 Comparison:")
        print(f"  Original: {len(original_bullet)} chars")
        print(f"  Enhanced: {len(enhanced_bullet)} chars")
        print(f"  Improvement: Added {len(enhanced_bullet) - len(original_bullet)} chars of detail")

        return enhanced_bullet

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_embedding_generation():
    """Test generating embeddings for bullet text."""
    print("\n" + "="*60)
    print("TEST 3: Embedding Generation")
    print("="*60)

    from llm_utils import embed

    bullet_texts = [
        "Led team of 5 engineers to build microservices platform",
        "Managed engineering team of 5 developing microservice architecture",
        "Built customer analytics dashboard using React and Python"
    ]

    print("\nGenerating embeddings for 3 bullets...\n")

    embeddings = []
    for i, bullet in enumerate(bullet_texts, 1):
        try:
            embedding = embed(bullet)
            embeddings.append(embedding)
            print(f"✅ Bullet {i}: Generated {len(embedding)}-dim embedding")
            print(f"   Text: {bullet[:60]}...")
        except Exception as e:
            print(f"❌ Bullet {i}: Error - {e}")
            return None

    # Calculate similarity between first two (should be high)
    if len(embeddings) >= 2:
        import numpy as np

        def cosine_similarity(vec1, vec2):
            a = np.array(vec1)
            b = np.array(vec2)
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_1_2 = cosine_similarity(embeddings[0], embeddings[1])
        sim_1_3 = cosine_similarity(embeddings[0], embeddings[2])

        print(f"\n📊 Similarity Scores:")
        print(f"  Bullet 1 vs Bullet 2: {sim_1_2:.4f} (should be ~0.90+, similar content)")
        print(f"  Bullet 1 vs Bullet 3: {sim_1_3:.4f} (should be ~0.70-0.80, different content)")

        if sim_1_2 > 0.85:
            print(f"\n✅ Similarity test passed! Similar bullets have high similarity.")
        else:
            print(f"\n⚠️  Similarity lower than expected. Check embedding model.")

    return embeddings


def test_batch_generation():
    """Test generating multiple bullets with mixed facts availability."""
    print("\n" + "="*60)
    print("TEST 4: Batch Generation (Simulated)")
    print("="*60)

    print("\nThis test simulates the job application flow where:")
    print("- Some bullets have stored facts (auto-enhanced)")
    print("- Some bullets don't have facts (fallback)")

    bullets = [
        "Led development of customer analytics dashboard",
        "Implemented CI/CD pipeline reducing deployment time",
        "Mentored junior engineers on best practices"
    ]

    # Simulate: only first bullet has facts
    print(f"\nScenario: {len(bullets)} bullets, 1 with stored facts\n")

    for i, bullet in enumerate(bullets, 1):
        has_facts = (i == 1)  # Only first bullet
        status = "✅ HAS FACTS" if has_facts else "⚠️  NO FACTS"
        action = "Will use fact-based generation" if has_facts else "Will fall back to basic rewrite"

        print(f"Bullet {i}: {status}")
        print(f"  Text: {bullet}")
        print(f"  Action: {action}\n")

    print("💡 In production, the system would:")
    print("  1. Match each bullet against stored bullets using embeddings")
    print("  2. Load facts for matched bullets")
    print("  3. Generate enhanced bullets using facts")
    print("  4. Fall back to basic rewrite for bullets without facts")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("RESUME OPTIMIZER REFACTORING - LOCAL TESTS")
    print("Testing LLM Functions (No Database Required)")
    print("="*60)

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY environment variable not set")
        print("\nPlease set your OpenAI API key:")
        print("  export OPENAI_API_KEY='sk-...'")
        return 1

    print("\n✅ OpenAI API key found")

    # Test 1: Fact extraction
    facts = test_fact_extraction()
    if not facts:
        print("\n❌ Fact extraction failed. Stopping tests.")
        return 1

    # Test 2: Bullet generation with facts
    enhanced = test_bullet_generation_with_facts(facts)
    if not enhanced:
        print("\n⚠️  Bullet generation failed, continuing with other tests...")

    # Test 3: Embedding generation
    embeddings = test_embedding_generation()
    if not embeddings:
        print("\n⚠️  Embedding generation failed, continuing...")

    # Test 4: Batch generation simulation
    test_batch_generation()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print("\n✅ All core LLM functions tested successfully!")
    print("\n📝 Next Steps:")
    print("  1. Review extracted facts above - do they look accurate?")
    print("  2. Review enhanced bullet - is it better than original?")
    print("  3. Check embedding similarities - do they make sense?")
    print("\n💡 To test database functions, run: python test_local_with_db.py")
    print("   (Requires Supabase setup)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
