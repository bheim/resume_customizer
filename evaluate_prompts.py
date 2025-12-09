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

import csv
import json
import sys
import argparse
from typing import Dict, List, Any
from datetime import datetime
from config import client, CHAT_MODEL, log
from llm_utils import (
    generate_bullet_with_facts,
    generate_bullet_with_facts_scaffolded,
    generate_bullet_self_critique,
    generate_bullet_multi_candidate,
    generate_bullet_hiring_manager,
    generate_bullet_jd_mirror,
    generate_bullet_combined,
    generate_bullets_batch,
)
from json import loads
import re


def load_bullets_from_csv(csv_path: str = "bullets.csv") -> List[Dict]:
    """Load bullets and their facts from CSV file."""
    bullets = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse pipe-delimited multi-value fields
            has_context = row['has_context'].lower() == 'true'

            facts = {}
            if has_context:
                facts = {
                    'tools': [t.strip() for t in row['tools'].split('|') if t.strip()],
                    'skills': [s.strip() for s in row['skills'].split('|') if s.strip()],
                    'actions': [a.strip() for a in row['actions'].split('|') if a.strip()],
                    'results': [r.strip() for r in row['results'].split('|') if r.strip()],
                    'timeline': row['timeline'].strip() if row['timeline'] else '',
                    'situation': row['situation'].strip() if row['situation'] else ''
                }

            bullets.append({
                'id': row['id'],
                'bullet': row['bullet_text'],
                'has_context': has_context,
                'facts': facts
            })

    return bullets


def load_jobs_from_csv(csv_path: str = "jobs.csv") -> List[Dict]:
    """Load job descriptions from CSV file."""
    jobs = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append({
                'id': row['id'],
                'title': row['title'],
                'type': row['type'],
                'description': row['description']
            })

    return jobs


def llm_judge_single_bullet(
    bullet: str,
    jd: str,
    jd_type: str,
    has_context: bool,
    bullet_label: str = "BULLET",
    original_bullet: str = None,
    facts: Dict = None
) -> Dict[str, Any]:
    """
    Use LLM as judge to evaluate a single bullet.

    Scores on 6 dimensions (1-10 each):
    1. Relevance to JD
    2. Conciseness (punchy vs verbose)
    3. Impact/Metrics clarity
    4. Action verb strength
    5. Factual accuracy (compared to source material)
    6. JD keyword alignment
    """

    # Build source material section for factual accuracy check
    if original_bullet and bullet_label == "OPTIMIZED":
        if has_context and facts:
            facts_text = []
            if facts.get("situation"): facts_text.append(f"Context: {facts['situation']}")
            if facts.get("actions"): facts_text.append(f"Actions: {'; '.join(facts['actions'])}")
            if facts.get("results"): facts_text.append(f"Results: {'; '.join(facts['results'])}")
            if facts.get("skills"): facts_text.append(f"Skills: {', '.join(facts['skills'])}")
            if facts.get("tools"): facts_text.append(f"Tools: {', '.join(facts['tools'])}")
            source_section = f"""
SOURCE MATERIAL (for factual accuracy check):
Original bullet: {original_bullet}
Verified facts:
{chr(10).join(facts_text) if facts_text else 'None provided'}
"""
        else:
            source_section = f"""
SOURCE MATERIAL (for factual accuracy check):
Original bullet: {original_bullet}
(No additional facts provided - optimized should NOT add any information)
"""
        factual_instruction = """5. **Factual Accuracy** (1-10) - COMPARE TO SOURCE ABOVE
   - Does the optimized bullet contain ONLY information from the source material?
   - Any added metrics, tools, or details = LOW SCORE (1-4)
   - Rephrasing is OK, inventing is NOT
   - This is the MOST IMPORTANT dimension"""
    else:
        source_section = ""
        factual_instruction = """5. **Factual Accuracy** (1-10)
   - Does this bullet seem grounded and believable?
   - Score based on specificity vs vagueness"""

    prompt = f"""You are evaluating a resume bullet for quality.

{bullet_label}:
{bullet}
{source_section}
JOB TYPE: {jd_type}
JOB DESCRIPTION:
{jd}

---

Score this bullet on these 6 dimensions (1-10 scale):

1. **Relevance to JD** (1-10)
   - Does it align with the job's key responsibilities?
   - Would a hiring manager see this as relevant?

2. **Conciseness** (1-10)
   - Tight and punchy, or verbose?
   - Does it end strong or trail off?

3. **Impact & Metrics** (1-10)
   - Are achievements clear?
   - Is business impact evident?

4. **Action Verbs** (1-10)
   - Strong ownership (Developed, Led, Built)?
   - Or weak verbs (Helped, Supported)?

{factual_instruction}

6. **JD Keyword Alignment** (1-10)
   - Uses relevant JD terminology?

---

Return ONLY valid JSON:

{{
  "relevance": X,
  "conciseness": X,
  "impact": X,
  "action_verbs": X,
  "factual_accuracy": X,
  "keyword_alignment": X,
  "total": X.X (average of above 6),
  "reasoning": "2-3 sentence explanation",
  "issues": ["specific", "problems"],
  "strengths": ["what", "worked"]
}}

Be strict. If optimized bullet added information not in source, factual_accuracy must be 1-4."""

    try:
        r = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        raw = (r.content[0].text or "").strip()

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


def compare_bullets(
    original: str,
    optimized: str,
    jd: str,
    jd_type: str,
    has_context: bool,
    verbose: bool = False,
    facts: Dict = None
) -> Dict[str, Any]:
    """
    Score both original and optimized bullets, return both scores + deltas.
    Now passes original bullet and facts to judge for proper factual accuracy assessment.
    """
    if verbose:
        print(f"  Scoring ORIGINAL bullet...")
    baseline = llm_judge_single_bullet(original, jd, jd_type, has_context, "ORIGINAL")

    if verbose:
        print(f"  Scoring OPTIMIZED bullet...")
    # Pass original and facts so judge can check for hallucination
    optimized_scores = llm_judge_single_bullet(
        optimized, jd, jd_type, has_context, "OPTIMIZED",
        original_bullet=original, facts=facts
    )

    # Calculate deltas
    dimensions = ["relevance", "conciseness", "impact", "action_verbs", "factual_accuracy", "keyword_alignment"]
    deltas = {}
    for dim in dimensions:
        deltas[dim] = optimized_scores.get(dim, 0) - baseline.get(dim, 0)

    deltas["total"] = optimized_scores.get("total", 0) - baseline.get("total", 0)

    return {
        "baseline": baseline,
        "optimized": optimized_scores,
        "deltas": deltas
    }


def run_evaluation(bullets_csv: str = "bullets.csv", jobs_csv: str = "jobs.csv", verbose: bool = False, approach: str = "all") -> Dict[str, List[Dict]]:
    """
    Run full evaluation across all bullets and job types.

    Args:
        approach: "single", "scaffolded", "self_critique", "multi_candidate",
                  "hiring_manager", "jd_mirror", "all", or "experimental" (new 4 only)

    Returns:
        Dict with results per approach
    """

    # Define all available approaches
    ALL_APPROACHES = {
        "single_stage": generate_bullet_with_facts,
        "scaffolded": generate_bullet_with_facts_scaffolded,
        "self_critique": generate_bullet_self_critique,
        "multi_candidate": generate_bullet_multi_candidate,
        "hiring_manager": generate_bullet_hiring_manager,
        "jd_mirror": generate_bullet_jd_mirror,
        "combined": generate_bullet_combined,
    }

    # Batch approach requires special handling (defined below)
    BATCH_APPROACH = "batch"

    EXPERIMENTAL = ["self_critique", "multi_candidate", "hiring_manager", "jd_mirror"]
    NEW_APPROACHES = ["combined", "batch"]  # The two newest approaches
    BASELINE = ["single_stage", "scaffolded"]

    print(f"\n{'='*80}")
    print("PROMPT EVALUATION - Head-to-Head Comparison")
    print(f"Testing: {approach.upper()} approach(es)")
    print(f"{'='*80}\n")

    # Load CSV files
    bullets = load_bullets_from_csv(bullets_csv)
    job_descriptions = load_jobs_from_csv(jobs_csv)

    results_by_approach = {}

    # Determine which approaches to test
    approaches_to_test = []
    include_batch = False

    if approach == "all":
        approaches_to_test = [(name, func) for name, func in ALL_APPROACHES.items()]
        include_batch = True
    elif approach == "experimental":
        approaches_to_test = [(name, ALL_APPROACHES[name]) for name in EXPERIMENTAL]
    elif approach == "baseline":
        approaches_to_test = [(name, ALL_APPROACHES[name]) for name in BASELINE]
    elif approach == "new":
        approaches_to_test = [(name, ALL_APPROACHES[name]) for name in NEW_APPROACHES if name in ALL_APPROACHES]
        include_batch = True
    elif approach == "batch":
        include_batch = True
    elif approach in ALL_APPROACHES:
        approaches_to_test = [(approach, ALL_APPROACHES[approach])]
    else:
        # Legacy support
        if approach in ["single", "both"]:
            approaches_to_test.append(("single_stage", generate_bullet_with_facts))
        if approach in ["scaffolded", "both"]:
            approaches_to_test.append(("scaffolded", generate_bullet_with_facts_scaffolded))

    for approach_name, generator_func in approaches_to_test:
        print(f"\n{'='*80}")
        print(f"TESTING: {approach_name.upper().replace('_', ' ')}")
        print(f"{'='*80}\n")

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
            print(f"Has Context: {'✅ YES' if has_context else '❌ NO'}")
            print(f"Original: {bullet_text[:100]}...")
            print(f"{'─'*80}\n")

            for jd in job_descriptions:
                test_num += 1
                jd_id = jd['id']
                jd_type = jd['type']
                jd_title = jd['title']
                jd_text = jd['description']

                print(f"[{test_num}/{total_tests}] {jd_title} ({jd_type})")

                try:
                    # Generate optimized bullet using current approach
                    print(f"  Generating optimized bullet...")
                    optimized = generator_func(bullet_text, jd_text, facts)

                    if verbose:
                        print(f"  Original:  {bullet_text}")
                        print(f"  Optimized: {optimized}")

                    # Compare original vs optimized (gets baseline, optimized scores, and deltas)
                    comparison = compare_bullets(
                        bullet_text, optimized, jd_text, jd_type, has_context, verbose,
                        facts=facts  # Pass facts for proper factual accuracy assessment
                    )

                    baseline = comparison['baseline']
                    optimized_scores = comparison['optimized']
                    deltas = comparison['deltas']

                    # Print summary with deltas
                    delta_total = deltas['total']
                    delta_str = f"+{delta_total:.1f}" if delta_total > 0 else f"{delta_total:.1f}"

                    print(f"  Baseline: {baseline['total']:.1f}/10 → Optimized: {optimized_scores['total']:.1f}/10 ({delta_str})")
                    print(f"    Rel: {baseline['relevance']}→{optimized_scores['relevance']} ({deltas['relevance']:+.0f}) | " +
                          f"Conc: {baseline['conciseness']}→{optimized_scores['conciseness']} ({deltas['conciseness']:+.0f}) | " +
                          f"Impact: {baseline['impact']}→{optimized_scores['impact']} ({deltas['impact']:+.0f})")
                    print(f"    Verbs: {baseline['action_verbs']}→{optimized_scores['action_verbs']} ({deltas['action_verbs']:+.0f}) | " +
                          f"Factual: {baseline['factual_accuracy']}→{optimized_scores['factual_accuracy']} ({deltas['factual_accuracy']:+.0f}) | " +
                          f"KW: {baseline['keyword_alignment']}→{optimized_scores['keyword_alignment']} ({deltas['keyword_alignment']:+.0f})")

                    if verbose and optimized_scores.get('issues'):
                        print(f"  Issues: {', '.join(optimized_scores['issues'][:2])}")

                    # Store result
                    results.append({
                        'bullet_id': bullet_id,
                        'has_context': has_context,
                        'jd_id': jd_id,
                        'jd_type': jd_type,
                        'jd_title': jd_title,
                        'original': bullet_text,
                        'optimized': optimized,
                        'baseline_scores': baseline,
                        'optimized_scores': optimized_scores,
                        'deltas': deltas,
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
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })

        results_by_approach[approach_name] = results

    # Handle batch approach separately (processes all bullets together per JD)
    if include_batch:
        print(f"\n{'='*80}")
        print(f"TESTING: BATCH (processes all bullets together)")
        print(f"{'='*80}\n")

        results = []
        test_num = 0

        for jd in job_descriptions:
            jd_id = jd['id']
            jd_type = jd['type']
            jd_title = jd['title']
            jd_text = jd['description']

            print(f"\n{'─'*80}")
            print(f"JOB: {jd_title} ({jd_type})")
            print(f"Processing {len(bullets)} bullets as a batch...")
            print(f"{'─'*80}\n")

            try:
                # Prepare batch data
                bullets_data = [
                    {"original_bullet": b['bullet'], "stored_facts": b['facts']}
                    for b in bullets
                ]

                # Generate all bullets together
                optimized_bullets = generate_bullets_batch(bullets_data, jd_text)

                # Score each bullet individually
                for i, (bullet_data, optimized) in enumerate(zip(bullets, optimized_bullets)):
                    test_num += 1
                    bullet_id = bullet_data['id']
                    bullet_text = bullet_data['bullet']
                    has_context = bullet_data['has_context']
                    facts = bullet_data['facts']

                    print(f"[{test_num}] {bullet_id}")

                    if verbose:
                        print(f"  Original:  {bullet_text}")
                        print(f"  Optimized: {optimized}")

                    # Compare original vs optimized
                    comparison = compare_bullets(
                        bullet_text, optimized, jd_text, jd_type, has_context, verbose,
                        facts=facts
                    )

                    baseline = comparison['baseline']
                    optimized_scores = comparison['optimized']
                    deltas = comparison['deltas']

                    delta_total = deltas['total']
                    delta_str = f"+{delta_total:.1f}" if delta_total > 0 else f"{delta_total:.1f}"

                    print(f"  Baseline: {baseline['total']:.1f}/10 → Optimized: {optimized_scores['total']:.1f}/10 ({delta_str})")

                    results.append({
                        'bullet_id': bullet_id,
                        'has_context': has_context,
                        'jd_id': jd_id,
                        'jd_type': jd_type,
                        'jd_title': jd_title,
                        'original': bullet_text,
                        'optimized': optimized,
                        'baseline_scores': baseline,
                        'optimized_scores': optimized_scores,
                        'deltas': deltas,
                        'timestamp': datetime.now().isoformat()
                    })

            except Exception as e:
                log.exception(f"Error in batch processing for {jd_id}: {e}")
                print(f"  ❌ ERROR: {str(e)}")

        results_by_approach["batch"] = results

    return results_by_approach


def print_summary(results_by_approach: Dict[str, List[Dict]]):
    """Print aggregated summary of evaluation results with head-to-head comparison."""

    print(f"\n\n{'='*80}")
    print("EVALUATION SUMMARY - HEAD-TO-HEAD COMPARISON")
    print(f"{'='*80}\n")

    # For each approach, print summary
    for approach_name, results in results_by_approach.items():
        print(f"\n{'─'*80}")
        print(f"{approach_name.upper().replace('_', ' ')} RESULTS")
        print(f"{'─'*80}\n")

        total_tests = len(results)
        valid_results = [r for r in results if 'deltas' in r]

        if not valid_results:
            print("  No valid results")
            continue

        # Calculate average scores and improvements
        avg_baseline = sum(r['baseline_scores']['total'] for r in valid_results) / len(valid_results)
        avg_optimized = sum(r['optimized_scores']['total'] for r in valid_results) / len(valid_results)
        avg_delta = sum(r['deltas']['total'] for r in valid_results) / len(valid_results)

        print(f"Total Tests: {total_tests}")
        print(f"Average Baseline:  {avg_baseline:.2f}/10")
        print(f"Average Optimized: {avg_optimized:.2f}/10")
        print(f"Average Delta:     {avg_delta:+.2f} points\n")

        # Delta distribution
        improvements = sum(1 for r in valid_results if r['deltas']['total'] > 0)
        no_change = sum(1 for r in valid_results if r['deltas']['total'] == 0)
        regressions = sum(1 for r in valid_results if r['deltas']['total'] < 0)

        print("Improvement Distribution:")
        print(f"  Improved:   {improvements:3d} ({improvements/len(valid_results)*100:5.1f}%)")
        print(f"  No change:  {no_change:3d} ({no_change/len(valid_results)*100:5.1f}%)")
        print(f"  Regressed:  {regressions:3d} ({regressions/len(valid_results)*100:5.1f}%)\n")

        # By context type
        with_context = [r for r in valid_results if r['has_context']]
        without_context = [r for r in valid_results if not r['has_context']]

        if with_context:
            avg_delta_with = sum(r['deltas']['total'] for r in with_context) / len(with_context)
            print(f"WITH Context:    Δ {avg_delta_with:+.2f} points (n={len(with_context)})")

        if without_context:
            avg_delta_without = sum(r['deltas']['total'] for r in without_context) / len(without_context)
            print(f"WITHOUT Context: Δ {avg_delta_without:+.2f} points (n={len(without_context)})\n")

        # Dimension breakdown
        print("Average Delta by Dimension:")
        dimensions = ['relevance', 'conciseness', 'impact', 'action_verbs', 'factual_accuracy', 'keyword_alignment']
        for dim in dimensions:
            deltas = [r['deltas'][dim] for r in valid_results]
            avg = sum(deltas) / len(deltas) if deltas else 0
            print(f"  {dim:20s}: {avg:+.2f}")
        print()

        # Best improvements
        print("Biggest Improvements:")
        best = sorted(valid_results, key=lambda x: x['deltas']['total'], reverse=True)[:5]
        for r in best:
            delta = r['deltas']['total']
            print(f"  {delta:+.1f} | {r['bullet_id']:30s} | {r['jd_type']}")

        print()

        # Worst cases (regressions or no improvement)
        print("Cases Needing Attention (lowest delta):")
        worst = sorted(valid_results, key=lambda x: x['deltas']['total'])[:5]
        for r in worst:
            delta = r['deltas']['total']
            print(f"  {delta:+.1f} | {r['bullet_id']:30s} | {r['jd_type']}")

    # If comparing multiple approaches, show leaderboard
    if len(results_by_approach) >= 2:
        print(f"\n{'='*80}")
        print("LEADERBOARD - APPROACH COMPARISON")
        print(f"{'='*80}\n")

        # Calculate stats for each approach
        approach_stats = []
        for name, results in results_by_approach.items():
            valid = [r for r in results if 'deltas' in r]
            if valid:
                avg_delta = sum(r['deltas']['total'] for r in valid) / len(valid)
                avg_optimized = sum(r['optimized_scores']['total'] for r in valid) / len(valid)
                improvements = sum(1 for r in valid if r['deltas']['total'] > 0)
                pct_improved = improvements / len(valid) * 100
                approach_stats.append({
                    'name': name,
                    'avg_delta': avg_delta,
                    'avg_optimized': avg_optimized,
                    'pct_improved': pct_improved,
                    'n': len(valid)
                })

        # Sort by avg_delta (best improvement first)
        approach_stats.sort(key=lambda x: x['avg_delta'], reverse=True)

        print(f"{'Rank':<5} {'Approach':<20} {'Avg Δ':>8} {'Avg Score':>10} {'% Improved':>12}")
        print("-" * 60)
        for i, stats in enumerate(approach_stats, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
            print(f"{medal}{i:<3} {stats['name']:<20} {stats['avg_delta']:>+7.2f} {stats['avg_optimized']:>9.2f} {stats['pct_improved']:>11.1f}%")

        print()

        # Show winner
        if approach_stats:
            winner = approach_stats[0]
            print(f"🏆 WINNER: {winner['name'].upper()}")
            print(f"   Average improvement: {winner['avg_delta']:+.2f} points")
            print(f"   Average optimized score: {winner['avg_optimized']:.2f}/10")
            print(f"   Improved {winner['pct_improved']:.1f}% of bullets")

    print(f"\n{'='*80}\n")


def save_results(results_by_approach: Dict[str, List[Dict]], output_path: str):
    """Save detailed results to JSON file."""
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'approaches': {}
    }

    for approach_name, results in results_by_approach.items():
        output_data['approaches'][approach_name] = {
            'total_tests': len(results),
            'results': results
        }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"✅ Detailed results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Evaluate prompt performance - Head-to-Head Comparison')
    parser.add_argument('--bullets', default='bullets.csv', help='Path to bullets CSV file')
    parser.add_argument('--jobs', default='jobs.csv', help='Path to jobs CSV file')
    parser.add_argument('--approach', default='all',
                       choices=['single_stage', 'scaffolded', 'self_critique', 'multi_candidate',
                                'hiring_manager', 'jd_mirror', 'combined', 'batch',
                                'all', 'experimental', 'baseline', 'new',
                                'single', 'both'],  # legacy support
                       help='Which approach(es) to test (default: all)')
    parser.add_argument('--save', help='Save detailed results to JSON file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    print("\nApproach options:")
    print("  all          - Test all 8 approaches")
    print("  new          - Test 2 newest approaches (combined, batch)")
    print("  experimental - Test 4 approaches (self_critique, multi_candidate, hiring_manager, jd_mirror)")
    print("  baseline     - Test 2 original approaches (single_stage, scaffolded)")
    print("  [name]       - Test specific approach (combined, batch, etc.)\n")

    # Run evaluation
    results_by_approach = run_evaluation(args.bullets, args.jobs, args.verbose, args.approach)

    # Print summary
    print_summary(results_by_approach)

    # Save if requested
    if args.save:
        save_results(results_by_approach, args.save)


if __name__ == "__main__":
    main()
