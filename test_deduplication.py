#!/usr/bin/env python3
"""
Test the deduplication functionality to verify it removes repetitive vocabulary.
"""

from llm_utils import optimize_keywords_light_touch, deduplicate_repeated_words

# Test data with job description that might cause repetition
job_description = """
Senior Data Analyst position requiring:
- Generate insights from complex datasets
- Develop analytical frameworks
- Create strategic recommendations
- Build data models and visualizations
- Conduct market analysis
"""

test_bullets = [
    "Built pricing framework to inform regional planning decisions across $500M portfolio",
    "Conducted market analysis to identify growth opportunities in cyber insurance segment",
    "Developed analytics solution to uncover retention drivers for 5,000+ users"
]

print("=" * 80)
print("DEDUPLICATION TEST")
print("=" * 80)
print()

print("ORIGINAL BULLETS:")
for i, bullet in enumerate(test_bullets, 1):
    print(f"{i}. {bullet}")
print()

# Step 1: Optimize individually (might create repetition)
print("STEP 1: Individual Optimization (may create repetition)")
print("-" * 80)
optimized_individually = []
for i, bullet in enumerate(test_bullets, 1):
    print(f"Optimizing bullet {i}...")
    optimized = optimize_keywords_light_touch(bullet, job_description)
    optimized_individually.append(optimized)
    print(f"  Result: {optimized}")
print()

# Check for repetition
print("CHECKING FOR REPETITION:")
print("-" * 80)
all_text = " ".join(optimized_individually).lower()
repetitive_words = ["generate", "generated", "develop", "developed", "create", "created", "build", "built", "conduct", "conducted"]

found_repetitions = []
for word in repetitive_words:
    count = all_text.count(word)
    if count > 1:
        found_repetitions.append(f"{word}: {count} times")

if found_repetitions:
    print("⚠️  REPETITION DETECTED:")
    for rep in found_repetitions:
        print(f"  - {rep}")
else:
    print("✓ No obvious repetition detected")
print()

# Step 2: Deduplicate
print("STEP 2: Deduplication Pass")
print("-" * 80)
deduplicated = deduplicate_repeated_words(optimized_individually, job_description)
print()

print("DEDUPLICATED BULLETS:")
for i, bullet in enumerate(deduplicated, 1):
    print(f"{i}. {bullet}")
print()

# Check for improvement
print("AFTER DEDUPLICATION:")
print("-" * 80)
all_text_after = " ".join(deduplicated).lower()

found_repetitions_after = []
for word in repetitive_words:
    count = all_text_after.count(word)
    if count > 1:
        found_repetitions_after.append(f"{word}: {count} times")

if found_repetitions_after:
    print("⚠️  Still some repetition:")
    for rep in found_repetitions_after:
        print(f"  - {rep}")
else:
    print("✓ No repetition detected - vocabulary is diverse!")
print()

# Compare before/after
print("COMPARISON:")
print("-" * 80)
print(f"Before deduplication: {len(found_repetitions)} repeated words")
print(f"After deduplication:  {len(found_repetitions_after)} repeated words")

if len(found_repetitions_after) < len(found_repetitions):
    print("✅ IMPROVEMENT: Repetition reduced!")
elif len(found_repetitions) == 0:
    print("✓ No repetition to begin with")
else:
    print("⚠️  No improvement or worse")

print()
print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
