#!/usr/bin/env python3
"""
Prompt Evaluation Script

Runs current prompts against test fixtures and uses LLM-as-judge to score results.
Tests both WITH-FACTS and NO-FACTS paths across 7 diverse job types.

Usage:
    python evaluate_prompts.py
    python evaluate_prompts.py --save results.json
    python evaluate_prompts.py --verbose
"""

import yaml
import json
import sys
import argparse
from typing import Dict, List, Any
from datetime import datetime
from config import client, CHAT_MODEL, log
from llm_utils import generate_bullet_with_facts
from json import loads
import re


def llm_judge_single_bullet(
    original: str,
    optimized: str,
    jd: str,
    jd_type: str,
    has_context: bool
) -> Dict[str, Any]:
    """
    Use LLM as judge to evaluate a single bullet optimization.

    Scores on 6 dimensions (1-10 each):
    1. Relevance to JD
    2. Conciseness (punchy vs verbose)
    3. Impact/Metrics clarity
    4. Action verb strength
    5. Factual accuracy (no hallucination if no context)
    6. JD keyword alignment
    """

    context_note = "NO CONTEXT PROVIDED - Check for hallucination!" if not has_context else "CONTEXT PROVIDED - Check facts adherence"

    prompt = f"""You are evaluating a resume bullet optimization for quality and adherence to guidelines.

ORIGINAL BULLET:
{original}

OPTIMIZED BULLET:
{optimized}

JOB TYPE: {jd_type}
JOB DESCRIPTION:
{jd}

EVALUATION CONTEXT:
{context_note}

---

Score the OPTIMIZED bullet on these 6 dimensions (1-10 scale):

1. **Relevance to JD** (1-10)
   - Does it align with the job's key skills, technologies, and responsibilities?
   - Would a hiring manager see this as relevant experience?

2. **Conciseness** (1-10)
   - Is it tight and punchy, or verbose with filler words?
   - Does it end strong, or trail off with vague clauses?
   - Are there unnecessary words like "comprehensive", "utilizing", "through data-driven insights"?

3. **Impact & Metrics** (1-10)
   - Are achievements quantified clearly?
   - Is the business impact evident?
   - Are metrics stated once in their most compelling form (not repeated)?

4. **Action Verbs** (1-10)
   - Strong ownership language (Developed, Led, Built)?
   - Or weak verbs (Helped with, Supported, Streamlined)?
   - Does it demonstrate initiative?

5. **Factual Accuracy** (1-10)
   {'- NO CONTEXT: Did it invent metrics, technologies, or details not in original?' if not has_context else '- WITH CONTEXT: Did it stick to provided facts without adding extras?'}
   {'- This is CRITICAL - any hallucination = instant low score' if not has_context else '- Should only use information from the verified facts'}

6. **JD Keyword Alignment** (1-10)
   - Does it use relevant terminology from the job description?
   - Are key technologies/skills mentioned (when appropriate)?

---

Return ONLY valid JSON (no commentary, no code fences):

{{
  "relevance": X,
  "conciseness": X,
  "impact": X,
  "action_verbs": X,
  "factual_accuracy": X,
  "keyword_alignment": X,
  "total": X.X (average of above 6),
  "reasoning": "2-3 sentence explanation of scores",
  "issues": ["list", "of", "specific", "problems"],
  "strengths": ["list", "of", "what", "worked", "well"]
}}

Be strict and objective. A mediocre bullet should score 5-6, not 8-9."""

    try:
        r = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        raw = (r.choices[0].message.content or "").strip()

        # Clean code fences if present
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = re.sub(r"^\s*json", "", raw, flags=re.I).strip()

        scores = loads(raw)

        # Calculate total if not provided
        if "total" not in scores:
            dimensions = ["relevance", "conciseness", "impact", "action_verbs", "factual_accuracy", "keyword_alignment"]
            total = sum(scores.get(d, 0) for d in dimensions) / len(dimensions)
            scores["total"] = round(total, 1)

        return scores

    except Exception as e:
        log.exception(f"Error in LLM judge: {e}")
        return {
            "relevance": 0, "conciseness": 0, "impact": 0,
            "action_verbs": 0, "factual_accuracy": 0, "keyword_alignment": 0,
            "total": 0, "reasoning": f"Error: {str(e)}",
            "issues": ["Judge evaluation failed"], "strengths": []
        }


def run_evaluation(fixtures_path: str = "test_fixtures.yaml", verbose: bool = False) -> List[Dict]:
    """Run full evaluation across all bullets and job types."""

    print(f"\n{'='*80}")
    print("PROMPT EVALUATION - Testing WITH-FACTS and NO-FACTS paths")
    print(f"{'='*80}\n")

    # Load fixtures
    with open(fixtures_path, 'r') as f:
        fixtures = yaml.safe_load(f)

    bullets = fixtures['bullets']
    job_descriptions = fixtures['job_descriptions']

    results = []
    total_tests = len(bullets) * len(job_descriptions)
    test_num = 0

    print(f"Running {total_tests} test cases ({len(bullets)} bullets × {len(job_descriptions)} job types)...\n")

    # Test each bullet against each job type
    for bullet_data in bullets:
        bullet_id = bullet_data['id']
        bullet_text = bullet_data['bullet']
        has_context = bullet_data['has_context']
        facts = bullet_data['facts']

        print(f"\n{'─'*80}")
        print(f"BULLET: {bullet_id}")
        print(f"Has Context: {'✅ YES' if has_context else '❌ NO (tests anti-hallucination)'}")
        print(f"Original: {bullet_text[:100]}...")
        print(f"{'─'*80}\n")

        for jd in job_descriptions:
            test_num += 1
            jd_id = jd['id']
            jd_type = jd['type']
            jd_title = jd['title']
            jd_text = jd['description']

            print(f"[{test_num}/{total_tests}] Testing against: {jd_title} ({jd_type})")

            try:
                # Generate optimized bullet
                optimized = generate_bullet_with_facts(bullet_text, jd_text, facts)

                if verbose:
                    print(f"  Original:  {bullet_text}")
                    print(f"  Optimized: {optimized}")

                # Judge the result
                scores = llm_judge_single_bullet(
                    bullet_text, optimized, jd_text, jd_type, has_context
                )

                # Print quick summary
                print(f"  Score: {scores['total']}/10 | " +
                      f"Rel:{scores['relevance']} Conc:{scores['conciseness']} " +
                      f"Impact:{scores['impact']} Verbs:{scores['action_verbs']} " +
                      f"Factual:{scores['factual_accuracy']} KW:{scores['keyword_alignment']}")

                if verbose and scores.get('issues'):
                    print(f"  Issues: {', '.join(scores['issues'][:2])}")

                # Store result
                results.append({
                    'bullet_id': bullet_id,
                    'has_context': has_context,
                    'jd_id': jd_id,
                    'jd_type': jd_type,
                    'jd_title': jd_title,
                    'original': bullet_text,
                    'optimized': optimized,
                    'scores': scores,
                    'timestamp': datetime.now().isoformat()
                })

            except Exception as e:
                log.exception(f"Error testing {bullet_id} with {jd_id}: {e}")
                print(f"  ❌ ERROR: {str(e)}")
                results.append({
                    'bullet_id': bullet_id,
                    'has_context': has_context,
                    'jd_id': jd_id,
                    'jd_type': jd_type,
                    'jd_title': jd_title,
                    'original': bullet_text,
                    'optimized': f"ERROR: {str(e)}",
                    'scores': {'total': 0, 'error': str(e)},
                    'timestamp': datetime.now().isoformat()
                })

    return results


def print_summary(results: List[Dict]):
    """Print aggregated summary of evaluation results."""

    print(f"\n\n{'='*80}")
    print("EVALUATION SUMMARY")
    print(f"{'='*80}\n")

    # Overall stats
    total_tests = len(results)
    avg_score = sum(r['scores'].get('total', 0) for r in results) / total_tests if total_tests > 0 else 0

    print(f"Total Tests: {total_tests}")
    print(f"Average Score: {avg_score:.2f}/10")
    print(f"")

    # Score distribution
    score_ranges = {'9-10': 0, '7-8.9': 0, '5-6.9': 0, '3-4.9': 0, '0-2.9': 0}
    for r in results:
        score = r['scores'].get('total', 0)
        if score >= 9: score_ranges['9-10'] += 1
        elif score >= 7: score_ranges['7-8.9'] += 1
        elif score >= 5: score_ranges['5-6.9'] += 1
        elif score >= 3: score_ranges['3-4.9'] += 1
        else: score_ranges['0-2.9'] += 1

    print("Score Distribution:")
    for range_name, count in score_ranges.items():
        pct = (count / total_tests * 100) if total_tests > 0 else 0
        print(f"  {range_name}: {count:3d} ({pct:5.1f}%)")
    print()

    # BY CONTEXT TYPE
    with_context = [r for r in results if r['has_context']]
    without_context = [r for r in results if not r['has_context']]

    avg_with = sum(r['scores'].get('total', 0) for r in with_context) / len(with_context) if with_context else 0
    avg_without = sum(r['scores'].get('total', 0) for r in without_context) / len(without_context) if without_context else 0

    print("By Context Type:")
    print(f"  WITH Context:    {avg_with:.2f}/10 (n={len(with_context)})")
    print(f"  WITHOUT Context: {avg_without:.2f}/10 (n={len(without_context)})")
    print()

    # BY JOB TYPE
    print("By Job Type:")
    job_types = {}
    for r in results:
        jt = r['jd_type']
        if jt not in job_types:
            job_types[jt] = []
        job_types[jt].append(r['scores'].get('total', 0))

    for jt, scores in sorted(job_types.items()):
        avg = sum(scores) / len(scores) if scores else 0
        print(f"  {jt:25s}: {avg:.2f}/10 (n={len(scores)})")
    print()

    # DIMENSION BREAKDOWN
    print("Average Dimension Scores:")
    dimensions = ['relevance', 'conciseness', 'impact', 'action_verbs', 'factual_accuracy', 'keyword_alignment']
    for dim in dimensions:
        scores = [r['scores'].get(dim, 0) for r in results]
        avg = sum(scores) / len(scores) if scores else 0
        print(f"  {dim:20s}: {avg:.2f}/10")
    print()

    # WORST PERFORMERS (need attention)
    print("Lowest Scoring Cases (need prompt improvement):")
    worst = sorted(results, key=lambda x: x['scores'].get('total', 0))[:5]
    for r in worst:
        print(f"  {r['scores'].get('total', 0):.1f}/10 | {r['bullet_id']:30s} | {r['jd_type']}")
        if r['scores'].get('issues'):
            print(f"         Issues: {', '.join(r['scores']['issues'][:2])}")
    print()

    # BEST PERFORMERS
    print("Highest Scoring Cases:")
    best = sorted(results, key=lambda x: x['scores'].get('total', 0), reverse=True)[:5]
    for r in best:
        print(f"  {r['scores'].get('total', 0):.1f}/10 | {r['bullet_id']:30s} | {r['jd_type']}")

    print(f"\n{'='*80}\n")


def save_results(results: List[Dict], output_path: str):
    """Save detailed results to JSON file."""
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'total_tests': len(results),
        'results': results
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"✅ Detailed results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Evaluate prompt performance')
    parser.add_argument('--fixtures', default='test_fixtures.yaml', help='Path to test fixtures')
    parser.add_argument('--save', help='Save detailed results to JSON file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Run evaluation
    results = run_evaluation(args.fixtures, args.verbose)

    # Print summary
    print_summary(results)

    # Save if requested
    if args.save:
        save_results(results, args.save)


if __name__ == "__main__":
    main()
