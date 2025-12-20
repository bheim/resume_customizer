#!/usr/bin/env python3
"""Test the new conservative keyword optimization approaches."""

import csv
import json
import re
from llm_utils import optimize_keywords_synonym_only, optimize_keywords_light_touch, optimize_keywords_one_change
from config import client, CHAT_MODEL

# Load bullets
bullets = []
with open("bullets.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        bullets.append({
            "id": row["id"],
            "text": row["bullet_text"]
        })

# Load jobs
jobs = []
with open("jobs.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        jobs.append({
            "id": row["id"],
            "title": row["title"],
            "desc": row["description"]
        })

# LLM Judge for keyword optimization
def judge_optimization(original, optimized, job_desc):
    prompt = f"""Score this keyword optimization on two dimensions.

ORIGINAL BULLET:
{original}

OPTIMIZED BULLET:
{optimized}

JOB DESCRIPTION:
{job_desc}

Score each dimension 1-10:

1. FACTUAL_PRESERVATION: Does the optimized bullet describe the EXACT same work as the original?
   - 10: Identical meaning, just different words
   - 7-9: Minor phrasing changes, same core facts
   - 4-6: Some added context that may or may not be accurate
   - 1-3: Adds claims, tools, metrics, or audiences not in original

2. KEYWORD_IMPROVEMENT: How well does it incorporate JD keywords?
   - 10: Excellent keyword alignment
   - 7-9: Good keyword incorporation
   - 4-6: Some keywords added
   - 1-3: Minimal or no improvement

Return ONLY valid JSON in this exact format: {{"factual": X, "keyword": Y}}"""

    r = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    text = r.content[0].text.strip()
    match = re.search(r"\{[^}]+\}", text)
    if match:
        return json.loads(match.group())
    return {"factual": 5, "keyword": 5}

# Test approaches
approaches = [
    ("synonym_only", optimize_keywords_synonym_only),
    ("light_touch", optimize_keywords_light_touch),
    ("one_change", optimize_keywords_one_change),
]

all_results = {}

for approach_name, func in approaches:
    print()
    print("=" * 80)
    print(f"TESTING: {approach_name.upper()}")
    print("=" * 80)

    results = []
    test_num = 0

    for bullet in bullets:
        for job in jobs:
            test_num += 1
            try:
                optimized = func(bullet["text"], job["desc"])
                scores = judge_optimization(bullet["text"], optimized, job["desc"])

                results.append({
                    "bullet_id": bullet["id"],
                    "job_id": job["id"],
                    "original": bullet["text"],
                    "optimized": optimized,
                    "factual": scores["factual"],
                    "keyword": scores["keyword"]
                })

                short_id = bullet["id"][:20]
                print(f"[{test_num}/36] {short_id} -> {job['id']}: F={scores['factual']}/10 K={scores['keyword']}/10")

            except Exception as e:
                print(f"[{test_num}/36] ERROR: {e}")
                results.append({
                    "bullet_id": bullet["id"],
                    "job_id": job["id"],
                    "error": str(e)
                })

    all_results[approach_name] = results

    # Summary
    valid = [r for r in results if "factual" in r]
    if valid:
        avg_factual = sum(r["factual"] for r in valid) / len(valid)
        avg_keyword = sum(r["keyword"] for r in valid) / len(valid)
        high_factual = sum(1 for r in valid if r["factual"] >= 8)
        print(f"\nSUMMARY: Avg Factual={avg_factual:.1f}, Avg Keyword={avg_keyword:.1f}, High Factual (>=8): {high_factual}/{len(valid)}")

# Save results
with open("new_approaches_results.json", "w") as f:
    json.dump(all_results, f, indent=2)

print()
print("=" * 80)
print("RESULTS SAVED TO: new_approaches_results.json")
print("=" * 80)
