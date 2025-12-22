#!/usr/bin/env python3
"""
Quick test script for the bullet edit/validation endpoint.

This tests that:
1. The endpoint is accessible
2. It accepts the correct request format
3. It validates and processes edited bullets
4. It applies character limits correctly
"""

import requests
import json

# Test configuration
BASE_URL = "http://localhost:8000"
ENDPOINT = "/v2/bullets/edit"

def test_bullet_edit_within_limit():
    """Test editing a bullet that stays within character limit."""

    print("=" * 80)
    print("TEST 1: Bullet Edit Within Character Limit")
    print("=" * 80)
    print()

    test_request = {
        "bullet_text": "Led analytics team to drive $2M revenue growth through data-driven insights",
        "original_bullet_text": "Led analytics team to drive revenue growth through insights"
    }

    url = f"{BASE_URL}{ENDPOINT}"
    print(f"Endpoint: {url}")
    print(f"Bullet text: {test_request['bullet_text']}")
    print(f"Original length: {len(test_request['original_bullet_text'])}")
    print()

    # Make request
    try:
        response = requests.post(
            url,
            json=test_request,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to server. Is it running?")
        print(f"   Try: uvicorn app:app --reload")
        return False
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out")
        return False

    # Check response
    print(f"Status Code: {response.status_code}")

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

    print()
    print("Response:")
    print(f"  Validated text: {result['validated_text']}")
    print(f"  Character count: {result['char_count']}")
    print(f"  Character limit: {result['char_limit']}")
    print(f"  Exceeds limit: {result['exceeds_limit']}")
    print(f"  Was shortened: {result['was_shortened']}")
    print()

    # Validate response
    if result['exceeds_limit']:
        print("❌ FAILED: Should not exceed limit")
        return False

    if result['was_shortened']:
        print("❌ FAILED: Should not be shortened")
        return False

    if result['char_count'] > result['char_limit']:
        print("❌ FAILED: Char count exceeds limit")
        return False

    print("✅ TEST PASSED")
    print()
    return True


def test_bullet_edit_exceeds_limit():
    """Test editing a bullet that exceeds character limit."""

    print("=" * 80)
    print("TEST 2: Bullet Edit Exceeds Character Limit")
    print("=" * 80)
    print()

    # Create a bullet that exceeds typical 100-char limit
    long_bullet = "Led cross-functional analytics team of 12 data scientists and engineers to drive $2M+ annual revenue growth through advanced machine learning models, predictive analytics frameworks, and comprehensive data-driven strategic insights and actionable recommendations for senior executive leadership"

    test_request = {
        "bullet_text": long_bullet,
        "original_bullet_text": "Led analytics team to drive revenue growth"  # Short original -> 100 char limit
    }

    url = f"{BASE_URL}{ENDPOINT}"
    print(f"Endpoint: {url}")
    print(f"Bullet length: {len(test_request['bullet_text'])} chars")
    print(f"Original length: {len(test_request['original_bullet_text'])} chars")
    print()

    # Make request
    try:
        response = requests.post(
            url,
            json=test_request,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to server. Is it running?")
        return False

    # Check response
    print(f"Status Code: {response.status_code}")

    if response.status_code != 200:
        print("❌ FAILED: Non-200 status code")
        print(f"Response: {response.text}")
        return False

    # Parse response
    result = response.json()

    print()
    print("Response:")
    print(f"  Original length: {result['original_length']}")
    print(f"  Validated text: {result['validated_text']}")
    print(f"  Character count: {result['char_count']}")
    print(f"  Character limit: {result['char_limit']}")
    print(f"  Exceeds limit: {result['exceeds_limit']}")
    print(f"  Was shortened: {result['was_shortened']}")
    print()

    # Validate response
    if not result['exceeds_limit']:
        print("❌ FAILED: Should exceed limit")
        return False

    if not result['was_shortened']:
        print("❌ FAILED: Should be shortened")
        return False

    if result['char_count'] > result['char_limit']:
        print("❌ FAILED: Validated text still exceeds limit")
        return False

    print("✅ TEST PASSED")
    print()
    return True


def test_bullet_edit_no_original():
    """Test editing a bullet without providing original text."""

    print("=" * 80)
    print("TEST 3: Bullet Edit Without Original Text")
    print("=" * 80)
    print()

    test_request = {
        "bullet_text": "Built analytics platform to drive strategic decision-making"
    }

    url = f"{BASE_URL}{ENDPOINT}"
    print(f"Endpoint: {url}")
    print(f"Bullet text: {test_request['bullet_text']}")
    print(f"No original text provided (should use default limit)")
    print()

    # Make request
    try:
        response = requests.post(
            url,
            json=test_request,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to server.")
        return False

    # Check response
    print(f"Status Code: {response.status_code}")

    if response.status_code != 200:
        print("❌ FAILED: Non-200 status code")
        print(f"Response: {response.text}")
        return False

    # Parse response
    result = response.json()

    print()
    print("Response:")
    print(f"  Validated text: {result['validated_text']}")
    print(f"  Character count: {result['char_count']}")
    print(f"  Character limit: {result['char_limit']}")
    print()

    # Should use default limit (200 based on 150 original)
    if result['char_limit'] != 200:
        print("⚠️  WARNING: Expected default limit of 200")

    print("✅ TEST PASSED")
    print()
    return True


if __name__ == "__main__":
    print()
    print("=" * 80)
    print("TESTING BULLET EDIT/VALIDATION ENDPOINT")
    print("=" * 80)
    print()

    results = []
    results.append(("Within Limit", test_bullet_edit_within_limit()))
    results.append(("Exceeds Limit", test_bullet_edit_exceeds_limit()))
    results.append(("No Original", test_bullet_edit_no_original()))

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")

    all_passed = all(result[1] for result in results)
    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED")
        exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        exit(1)
