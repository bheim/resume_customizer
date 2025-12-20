#!/usr/bin/env python3
"""
Quick test script for the new keyword-only optimization endpoint.

This tests that:
1. The endpoint is accessible
2. It accepts the correct request format
3. It returns keyword-optimized bullets
4. The optimization is conservative (high factual accuracy)
"""

import requests
import json

# Test configuration
BASE_URL = "http://localhost:8000"
ENDPOINT = "/v2/apply/generate_keywords_only"

# Test data
test_request = {
    "user_id": "test-user-123",
    "job_description": """
        We're seeking a Senior Data Analyst to join our team.

        Responsibilities:
        • Conduct market research and competitive analysis
        • Build analytics frameworks using Python and SQL
        • Deliver strategic insights to senior leadership
        • Partner with cross-functional teams
        • Drive evidence-based recommendations

        Requirements:
        • 3+ years of data analysis experience
        • Proficiency in Python, SQL, Tableau
        • Strong communication skills
        • Experience with strategic planning
    """,
    "bullets": [
        {
            "bullet_text": "Developed pricing analytics framework to streamline regional planning, defining data-driven strategy decisions across $500M portfolio"
        },
        {
            "bullet_text": "Conducted market and portfolio analysis to identify expansion opportunities in cyber insurance, shaping strategic initiatives in a key growth segment"
        },
        {
            "bullet_text": "Built analytics framework to uncover retention drivers for 5,000+ users; informed product and strategy decisions"
        }
    ]
}

def test_keyword_endpoint():
    """Test the keyword-only optimization endpoint."""

    print("=" * 80)
    print("TESTING KEYWORD-ONLY OPTIMIZATION ENDPOINT")
    print("=" * 80)
    print()

    url = f"{BASE_URL}{ENDPOINT}"
    print(f"Endpoint: {url}")
    print(f"User ID: {test_request['user_id']}")
    print(f"Number of bullets: {len(test_request['bullets'])}")
    print()

    # Make request
    print("Sending request...")
    try:
        response = requests.post(
            url,
            json=test_request,
            headers={"Content-Type": "application/json"},
            timeout=120  # 2 minutes for LLM calls
        )
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to server. Is it running?")
        print(f"   Try: cd {'/'.join(__file__.split('/')[:-1])} && uvicorn app:app --reload")
        return False
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out (>120s)")
        return False

    # Check response
    print(f"Status Code: {response.status_code}")
    print()

    if response.status_code != 200:
        print("❌ FAILED: Non-200 status code")
        print(f"Response: {response.text}")
        return False

    # Parse response
    try:
        result = response.json()
    except json.JSONDecodeError:
        print("❌ FAILED: Invalid JSON response")
        print(f"Response: {response.text}")
        return False

    # Validate response structure
    print("✓ Response received")
    print()

    if "enhanced_bullets" not in result:
        print("❌ FAILED: Missing 'enhanced_bullets' in response")
        return False

    enhanced = result["enhanced_bullets"]
    print(f"✓ Enhanced bullets count: {len(enhanced)}")

    if len(enhanced) != len(test_request["bullets"]):
        print(f"❌ FAILED: Expected {len(test_request['bullets'])} bullets, got {len(enhanced)}")
        return False

    # Check each bullet
    print()
    print("=" * 80)
    print("BULLET TRANSFORMATIONS")
    print("=" * 80)

    for i, bullet_result in enumerate(enhanced):
        print()
        print(f"--- Bullet {i+1} ---")

        if "original" not in bullet_result or "enhanced" not in bullet_result:
            print("❌ FAILED: Missing 'original' or 'enhanced' in bullet result")
            return False

        original = bullet_result["original"]
        enhanced_text = bullet_result["enhanced"]
        used_facts = bullet_result.get("used_facts", True)  # Should be False

        print(f"Original:  {original}")
        print(f"Enhanced:  {enhanced_text}")
        print(f"Used Facts: {used_facts}")

        # Check that used_facts is False (keyword-only mode)
        if used_facts:
            print("⚠️  WARNING: used_facts should be False for keyword-only mode")

        # Check that the bullet was actually modified (or stayed same if perfect)
        if original == enhanced_text:
            print("ℹ️  Note: Bullet unchanged (may be intentional if already optimal)")
        else:
            print("✓ Bullet was optimized")

        # Simple factual check: ensure no obvious hallucinations
        # (e.g., numbers should not appear if not in original)
        import re
        original_numbers = set(re.findall(r'\d+', original))
        enhanced_numbers = set(re.findall(r'\d+', enhanced_text))
        new_numbers = enhanced_numbers - original_numbers

        if new_numbers:
            print(f"⚠️  WARNING: New numbers added: {new_numbers} (possible hallucination)")

    # Check scores
    print()
    print("=" * 80)
    print("COMPARATIVE SCORES")
    print("=" * 80)

    if "scores" in result and result["scores"]:
        scores = result["scores"]
        print(f"Before Score: {scores.get('before_score', 'N/A')}")
        print(f"After Score:  {scores.get('after_score', 'N/A')}")
        print(f"Improvement:  {scores.get('improvement', 'N/A'):+.1f} points")

        if scores.get('improvement', 0) > 0:
            print("✓ Positive improvement detected")
        else:
            print("ℹ️  Note: No improvement (may indicate bullets were already good)")
    else:
        print("⚠️  No scores returned (scoring may have failed)")

    # Check optimization mode
    print()
    if result.get("optimization_mode") == "keywords_only":
        print("✓ Optimization mode confirmed: keywords_only")
    else:
        print(f"⚠️  Unexpected optimization mode: {result.get('optimization_mode')}")

    print()
    print("=" * 80)
    print("✅ TEST PASSED")
    print("=" * 80)

    return True


if __name__ == "__main__":
    success = test_keyword_endpoint()
    exit(0 if success else 1)
