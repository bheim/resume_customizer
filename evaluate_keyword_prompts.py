#!/usr/bin/env python3
"""
Keyword Optimization Prompt Evaluation Script

Runs keyword-only optimization prompts against test fixtures and uses LLM-as-judge
to score results. This is specifically for testing keyword injection strategies,
NOT full resume optimization.

Key differences from evaluate_prompts.py:
- Focuses on keyword alignment as the PRIMARY metric
- Uses a keyword-specific scoring rubric
- Emphasizes factual preservation (no new information)
- Measures keyword density and relevance

Usage:
    python evaluate_keyword_prompts.py
    python evaluate_keyword_prompts.py --save keyword_results.json
    python evaluate_keyword_prompts.py --approach simple --verbose
"""

import csv
import json
import sys
import argparse
from typing import Dict, List, Any
from datetime import datetime
from config import client, CHAT_MODEL, log
from llm_utils import (
    optimize_keywords_simple,
    optimize_keywords_targeted,
    optimize_keywords_aggressive,
    optimize_keywords_with_context,
    optimize_keywords_hybrid,
    optimize_keywords_factual_first,
    optimize_keywords_synonym_only,
    optimize_keywords_light_touch,
    optimize_keywords_one_change,
)
from json import loads
import re


def load_bullets_from_csv(csv_path: str = "bullets.csv") -> List[Dict]:
    """Load bullets and their facts from CSV file."""
    bullets = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
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


def llm_judge_keyword_optimization(
    original_bullet: str,
    optimized_bullet: str,
    jd: str,
    jd_type: str,
) -> Dict[str, Any]:
    """
    LLM-as-judge specifically for keyword optimization.

    Scores on 4 keyword-specific dimensions (1-10 each):
    1. Keyword Alignment - How well does it match JD terminology?
    2. Factual Preservation - Did it keep the original meaning intact?
    3. Natural Flow - Does it read naturally (not keyword-stuffed)?
    4. ATS Optimization - Would this pass ATS screening better?

    Also extracts specific metrics:
    - Keywords added
    - Keywords from JD used
    - Words changed
    """

    prompt = f"""You are evaluating a KEYWORD OPTIMIZATION of a resume bullet.

The goal was to inject job description terminology while preserving the original meaning.

ORIGINAL BULLET:
{original_bullet}

OPTIMIZED BULLET:
{optimized_bullet}

JOB TYPE: {jd_type}
JOB DESCRIPTION:
{jd}

---

Score the keyword optimization on these 4 dimensions (1-10 scale):

1. **Keyword Alignment** (1-10) - MOST IMPORTANT
   - How many relevant JD keywords/phrases are now in the bullet?
   - Does it use the JD's specific terminology?
   - Are the keywords naturally integrated?
   - 10 = Excellent keyword coverage, 1 = No JD keywords used

2. **Factual Preservation** (1-10) - CRITICAL
   - Does the optimized bullet say the SAME thing as the original?
   - Were any facts, metrics, or claims ADDED that weren't in original?
   - Any added information = LOW SCORE (1-4)
   - 10 = Perfectly preserved meaning, 1 = Added false information

3. **Natural Flow** (1-10)
   - Does it read naturally, or is it awkwardly keyword-stuffed?
   - Is the sentence structure clear and professional?
   - 10 = Reads perfectly natural, 1 = Obvious keyword stuffing

4. **ATS Improvement** (1-10)
   - Would this version score better in ATS systems than the original?
   - Are important JD keywords now present that weren't before?
   - 10 = Significant ATS improvement, 1 = No improvement

---

Also identify:
- Keywords/phrases from the JD that were successfully incorporated
- Any words/phrases that were changed from original
- Any concerns about accuracy or keyword stuffing

Return ONLY valid JSON:

{{
  "keyword_alignment": X,
  "factual_preservation": X,
  "natural_flow": X,
  "ats_improvement": X,
  "total": X.X (weighted average: 40% keyword, 30% factual, 20% natural, 10% ats),
  "jd_keywords_used": ["keyword1", "keyword2", ...],
  "words_changed": ["original→new", ...],
  "concerns": ["specific concern 1", ...],
  "strengths": ["what worked well", ...]
}}

Be strict about factual preservation. If new claims were added, factual_preservation must be 1-4."""

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

        # Calculate weighted total if not provided
        if "total" not in scores:
            keyword = scores.get("keyword_alignment", 0)
            factual = scores.get("factual_preservation", 0)
            natural = scores.get("natural_flow", 0)
            ats = scores.get("ats_improvement", 0)
            total = keyword * 0.4 + factual * 0.3 + natural * 0.2 + ats * 0.1
            scores["total"] = round(total, 1)

        return scores

    except Exception as e:
        log.exception(f"Error in keyword judge: {e}")
        return {
            "keyword_alignment": 0,
            "factual_preservation": 0,
            "natural_flow": 0,
            "ats_improvement": 0,
            "total": 0,
            "jd_keywords_used": [],
            "words_changed": [],
            "concerns": [f"Judge evaluation failed: {str(e)}"],
            "strengths": []
        }


def score_baseline_bullet(
    bullet: str,
    jd: str,
    jd_type: str,
) -> Dict[str, Any]:
    """
    Score the ORIGINAL bullet for keyword alignment (baseline).

    This establishes how well the original bullet matches the JD
    before any optimization.
    """

    prompt = f"""You are evaluating a resume bullet's keyword alignment with a job description.

BULLET:
{bullet}

JOB TYPE: {jd_type}
JOB DESCRIPTION:
{jd}

---

Score this bullet on keyword alignment (1-10 scale):

1. **Keyword Alignment** (1-10)
   - How many relevant JD keywords/phrases are in the bullet?
   - Does it use the JD's specific terminology?
   - 10 = Excellent keyword coverage, 1 = No JD keywords used

Also identify:
- Which JD keywords/phrases are already present in the bullet
- Which important JD keywords are MISSING

Return ONLY valid JSON:

{{
  "keyword_alignment": X,
  "jd_keywords_present": ["keyword1", "keyword2", ...],
  "jd_keywords_missing": ["important missing keyword", ...]
}}"""

    try:
        r = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        raw = (r.content[0].text or "").strip()

        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = re.sub(r"^\s*json", "", raw, flags=re.I).strip()

        return loads(raw)

    except Exception as e:
        log.exception(f"Error in baseline scoring: {e}")
        return {
            "keyword_alignment": 0,
            "jd_keywords_present": [],
            "jd_keywords_missing": []
        }


def run_keyword_evaluation(
    bullets_csv: str = "bullets.csv",
    jobs_csv: str = "jobs.csv",
    verbose: bool = False,
    approach: str = "all"
) -> Dict[str, List[Dict]]:
    """
    Run keyword optimization evaluation across all bullets and job types.

    Args:
        approach: "simple", "targeted", "aggressive", "with_context", "hybrid", or "all"

    Returns:
        Dict with results per approach
    """

    # Define all keyword optimization approaches
    ALL_APPROACHES = {
        "simple": optimize_keywords_simple,
        "targeted": optimize_keywords_targeted,
        "aggressive": optimize_keywords_aggressive,
        "with_context": optimize_keywords_with_context,
        "hybrid": optimize_keywords_hybrid,
        "factual_first": optimize_keywords_factual_first,
        "synonym_only": optimize_keywords_synonym_only,
        "light_touch": optimize_keywords_light_touch,
        "one_change": optimize_keywords_one_change,
    }

    print(f"\n{'='*80}")
    print("KEYWORD OPTIMIZATION EVALUATION")
    print(f"Testing: {approach.upper()} approach(es)")
    print(f"{'='*80}\n")

    # Load CSV files
    bullets = load_bullets_from_csv(bullets_csv)
    job_descriptions = load_jobs_from_csv(jobs_csv)

    results_by_approach = {}

    # Determine which approaches to test
    if approach == "all":
        approaches_to_test = list(ALL_APPROACHES.items())
    elif approach in ALL_APPROACHES:
        approaches_to_test = [(approach, ALL_APPROACHES[approach])]
    else:
        print(f"Unknown approach: {approach}")
        print(f"Available: {', '.join(ALL_APPROACHES.keys())}, all")
        return {}

    for approach_name, optimizer_func in approaches_to_test:
        print(f"\n{'='*80}")
        print(f"TESTING: {approach_name.upper()}")
        print(f"{'='*80}\n")

        results = []
        total_tests = len(bullets) * len(job_descriptions)
        test_num = 0

        print(f"Running {total_tests} test cases ({len(bullets)} bullets x {len(job_descriptions)} job types)...\n")

        for bullet_data in bullets:
            bullet_id = bullet_data['id']
            bullet_text = bullet_data['bullet']
            has_context = bullet_data['has_context']
            facts = bullet_data['facts']

            print(f"\n{'-'*80}")
            print(f"BULLET: {bullet_id}")
            print(f"Has Context: {'YES' if has_context else 'NO'}")
            print(f"Original: {bullet_text[:100]}...")
            print(f"{'-'*80}\n")

            for jd in job_descriptions:
                test_num += 1
                jd_id = jd['id']
                jd_type = jd['type']
                jd_title = jd['title']
                jd_text = jd['description']

                print(f"[{test_num}/{total_tests}] {jd_title} ({jd_type})")

                try:
                    # Score baseline (original bullet)
                    if verbose:
                        print(f"  Scoring baseline...")
                    baseline = score_baseline_bullet(bullet_text, jd_text, jd_type)
                    baseline_kw = baseline.get('keyword_alignment', 0)

                    # Generate keyword-optimized bullet
                    if verbose:
                        print(f"  Optimizing keywords...")
                    optimized = optimizer_func(bullet_text, jd_text, facts)

                    if verbose:
                        print(f"  Original:  {bullet_text}")
                        print(f"  Optimized: {optimized}")

                    # Score the optimization
                    if verbose:
                        print(f"  Scoring optimization...")
                    scores = llm_judge_keyword_optimization(
                        bullet_text, optimized, jd_text, jd_type
                    )

                    # Calculate deltas
                    kw_delta = scores.get('keyword_alignment', 0) - baseline_kw

                    # Print summary
                    print(f"  Baseline KW: {baseline_kw}/10 -> Optimized: {scores.get('keyword_alignment', 0)}/10 ({kw_delta:+.0f})")
                    print(f"    Factual: {scores.get('factual_preservation', 0)}/10 | "
                          f"Natural: {scores.get('natural_flow', 0)}/10 | "
                          f"Total: {scores.get('total', 0):.1f}/10")

                    if scores.get('jd_keywords_used'):
                        print(f"    Keywords used: {', '.join(scores['jd_keywords_used'][:5])}")

                    if verbose and scores.get('concerns'):
                        print(f"    Concerns: {', '.join(scores['concerns'][:2])}")

                    # Store result
                    results.append({
                        'bullet_id': bullet_id,
                        'has_context': has_context,
                        'jd_id': jd_id,
                        'jd_type': jd_type,
                        'jd_title': jd_title,
                        'original': bullet_text,
                        'optimized': optimized,
                        'baseline_keyword_score': baseline_kw,
                        'baseline_keywords_present': baseline.get('jd_keywords_present', []),
                        'baseline_keywords_missing': baseline.get('jd_keywords_missing', []),
                        'optimized_scores': scores,
                        'keyword_delta': kw_delta,
                        'timestamp': datetime.now().isoformat()
                    })

                except Exception as e:
                    log.exception(f"Error testing {bullet_id} with {jd_id}: {e}")
                    print(f"  ERROR: {str(e)}")
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

    return results_by_approach


def print_keyword_summary(results_by_approach: Dict[str, List[Dict]]):
    """Print aggregated summary of keyword optimization results."""

    print(f"\n\n{'='*80}")
    print("KEYWORD OPTIMIZATION SUMMARY")
    print(f"{'='*80}\n")

    for approach_name, results in results_by_approach.items():
        print(f"\n{'-'*80}")
        print(f"{approach_name.upper()} RESULTS")
        print(f"{'-'*80}\n")

        valid_results = [r for r in results if 'optimized_scores' in r]

        if not valid_results:
            print("  No valid results")
            continue

        # Calculate averages
        avg_baseline = sum(r['baseline_keyword_score'] for r in valid_results) / len(valid_results)
        avg_optimized = sum(r['optimized_scores']['keyword_alignment'] for r in valid_results) / len(valid_results)
        avg_delta = sum(r['keyword_delta'] for r in valid_results) / len(valid_results)
        avg_factual = sum(r['optimized_scores']['factual_preservation'] for r in valid_results) / len(valid_results)
        avg_natural = sum(r['optimized_scores']['natural_flow'] for r in valid_results) / len(valid_results)
        avg_total = sum(r['optimized_scores']['total'] for r in valid_results) / len(valid_results)

        print(f"Total Tests: {len(valid_results)}")
        print(f"\nKEYWORD ALIGNMENT:")
        print(f"  Baseline Average:  {avg_baseline:.2f}/10")
        print(f"  Optimized Average: {avg_optimized:.2f}/10")
        print(f"  Average Delta:     {avg_delta:+.2f} points")

        print(f"\nOTHER DIMENSIONS:")
        print(f"  Factual Preservation: {avg_factual:.2f}/10")
        print(f"  Natural Flow:         {avg_natural:.2f}/10")
        print(f"  Total Score:          {avg_total:.2f}/10")

        # Improvement distribution
        improvements = sum(1 for r in valid_results if r['keyword_delta'] > 0)
        no_change = sum(1 for r in valid_results if r['keyword_delta'] == 0)
        regressions = sum(1 for r in valid_results if r['keyword_delta'] < 0)

        print(f"\nIMPROVEMENT DISTRIBUTION:")
        print(f"  Improved:  {improvements:3d} ({improvements/len(valid_results)*100:5.1f}%)")
        print(f"  No change: {no_change:3d} ({no_change/len(valid_results)*100:5.1f}%)")
        print(f"  Regressed: {regressions:3d} ({regressions/len(valid_results)*100:5.1f}%)")

        # Factual accuracy distribution
        high_factual = sum(1 for r in valid_results if r['optimized_scores']['factual_preservation'] >= 8)
        mid_factual = sum(1 for r in valid_results if 5 <= r['optimized_scores']['factual_preservation'] < 8)
        low_factual = sum(1 for r in valid_results if r['optimized_scores']['factual_preservation'] < 5)

        print(f"\nFACTUAL PRESERVATION:")
        print(f"  High (8-10): {high_factual:3d} ({high_factual/len(valid_results)*100:5.1f}%)")
        print(f"  Medium (5-7): {mid_factual:3d} ({mid_factual/len(valid_results)*100:5.1f}%)")
        print(f"  Low (1-4):   {low_factual:3d} ({low_factual/len(valid_results)*100:5.1f}%)")

        # By context type
        with_context = [r for r in valid_results if r['has_context']]
        without_context = [r for r in valid_results if not r['has_context']]

        if with_context:
            avg_delta_with = sum(r['keyword_delta'] for r in with_context) / len(with_context)
            print(f"\nWITH Context:    Keyword Delta {avg_delta_with:+.2f} (n={len(with_context)})")

        if without_context:
            avg_delta_without = sum(r['keyword_delta'] for r in without_context) / len(without_context)
            print(f"WITHOUT Context: Keyword Delta {avg_delta_without:+.2f} (n={len(without_context)})")

        # Best improvements
        print(f"\nBEST KEYWORD IMPROVEMENTS:")
        best = sorted(valid_results, key=lambda x: x['keyword_delta'], reverse=True)[:5]
        for r in best:
            delta = r['keyword_delta']
            factual = r['optimized_scores']['factual_preservation']
            print(f"  KW: {delta:+.0f} (Fact: {factual}/10) | {r['bullet_id'][:30]:30s} | {r['jd_type']}")

        # Worst cases
        print(f"\nCASES NEEDING ATTENTION:")
        worst = sorted(valid_results, key=lambda x: (
            x['optimized_scores']['factual_preservation'],
            x['keyword_delta']
        ))[:5]
        for r in worst:
            delta = r['keyword_delta']
            factual = r['optimized_scores']['factual_preservation']
            print(f"  KW: {delta:+.0f} (Fact: {factual}/10) | {r['bullet_id'][:30]:30s} | {r['jd_type']}")

    # Leaderboard if multiple approaches
    if len(results_by_approach) >= 2:
        print(f"\n{'='*80}")
        print("LEADERBOARD - KEYWORD OPTIMIZATION APPROACHES")
        print(f"{'='*80}\n")

        approach_stats = []
        for name, results in results_by_approach.items():
            valid = [r for r in results if 'optimized_scores' in r]
            if valid:
                avg_kw_delta = sum(r['keyword_delta'] for r in valid) / len(valid)
                avg_factual = sum(r['optimized_scores']['factual_preservation'] for r in valid) / len(valid)
                avg_total = sum(r['optimized_scores']['total'] for r in valid) / len(valid)
                improvements = sum(1 for r in valid if r['keyword_delta'] > 0)
                pct_improved = improvements / len(valid) * 100
                approach_stats.append({
                    'name': name,
                    'avg_kw_delta': avg_kw_delta,
                    'avg_factual': avg_factual,
                    'avg_total': avg_total,
                    'pct_improved': pct_improved,
                    'n': len(valid)
                })

        # Sort by total score (balances keyword improvement with factual accuracy)
        approach_stats.sort(key=lambda x: x['avg_total'], reverse=True)

        print(f"{'Rank':<5} {'Approach':<15} {'KW Delta':>10} {'Factual':>10} {'Total':>10} {'% Improved':>12}")
        print("-" * 65)
        for i, stats in enumerate(approach_stats, 1):
            medal = "1st" if i == 1 else "2nd" if i == 2 else "3rd" if i == 3 else f"{i}th"
            print(f"{medal:<5} {stats['name']:<15} {stats['avg_kw_delta']:>+9.2f} "
                  f"{stats['avg_factual']:>9.2f} {stats['avg_total']:>9.2f} {stats['pct_improved']:>11.1f}%")

        print()

        if approach_stats:
            winner = approach_stats[0]
            print(f"WINNER: {winner['name'].upper()}")
            print(f"  Keyword improvement: {winner['avg_kw_delta']:+.2f} points")
            print(f"  Factual preservation: {winner['avg_factual']:.2f}/10")
            print(f"  Total score: {winner['avg_total']:.2f}/10")
            print(f"  Improved {winner['pct_improved']:.1f}% of bullets")

    print(f"\n{'='*80}\n")


def save_keyword_results(results_by_approach: Dict[str, List[Dict]], output_path: str):
    """Save detailed keyword optimization results to JSON file."""
    output_data = {
        'timestamp': datetime.now().isoformat(),
        'evaluation_type': 'keyword_optimization',
        'approaches': {}
    }

    for approach_name, results in results_by_approach.items():
        output_data['approaches'][approach_name] = {
            'total_tests': len(results),
            'results': results
        }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"Detailed results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Evaluate keyword optimization prompts')
    parser.add_argument('--bullets', default='bullets.csv', help='Path to bullets CSV file')
    parser.add_argument('--jobs', default='jobs.csv', help='Path to jobs CSV file')
    parser.add_argument('--approach', default='all',
                       choices=['simple', 'targeted', 'aggressive', 'with_context', 'hybrid', 'factual_first', 'synonym_only', 'light_touch', 'one_change', 'all'],
                       help='Which approach(es) to test (default: all)')
    parser.add_argument('--save', help='Save detailed results to JSON file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    print("\nKeyword Optimization Approaches:")
    print("  simple       - Conservative synonym swapping only")
    print("  targeted     - Extract JD keywords, then inject")
    print("  aggressive   - Maximize keyword density")
    print("  with_context - Uses stored facts for keyword context")
    print("  hybrid       - Multi-candidate selection")
    print("  factual_first- Facts come first, minimal changes only")
    print("  synonym_only - ONLY 1:1 synonym swaps, nothing added")
    print("  light_touch  - Small adjustments with explicit guardrails")
    print("  one_change   - Exactly ONE safe keyword change")
    print("  all          - Test all 9 approaches\n")

    # Run evaluation
    results_by_approach = run_keyword_evaluation(
        args.bullets, args.jobs, args.verbose, args.approach
    )

    # Print summary
    print_keyword_summary(results_by_approach)

    # Save if requested
    if args.save:
        save_keyword_results(results_by_approach, args.save)


if __name__ == "__main__":
    main()
