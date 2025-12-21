#!/usr/bin/env python3
"""Summarize keyword optimization test results."""

import json
from typing import Dict, List

def load_results(filename: str) -> Dict:
    with open(filename, 'r') as f:
        return json.load(f)

def summarize_approach(approach_name: str, results: List[Dict]) -> Dict:
    """Calculate summary stats for an approach."""
    valid = [r for r in results if 'optimized_scores' in r]

    if not valid:
        return None

    avg_baseline = sum(r['baseline_keyword_score'] for r in valid) / len(valid)
    avg_optimized = sum(r['optimized_scores']['keyword_alignment'] for r in valid) / len(valid)
    avg_delta = sum(r['keyword_delta'] for r in valid) / len(valid)
    avg_factual = sum(r['optimized_scores']['factual_preservation'] for r in valid) / len(valid)
    avg_natural = sum(r['optimized_scores']['natural_flow'] for r in valid) / len(valid)
    avg_total = sum(r['optimized_scores']['total'] for r in valid) / len(valid)

    improvements = sum(1 for r in valid if r['keyword_delta'] > 0)
    pct_improved = improvements / len(valid) * 100

    high_factual = sum(1 for r in valid if r['optimized_scores']['factual_preservation'] >= 8)
    pct_high_factual = high_factual / len(valid) * 100

    return {
        'name': approach_name,
        'n': len(valid),
        'avg_baseline_kw': avg_baseline,
        'avg_optimized_kw': avg_optimized,
        'avg_kw_delta': avg_delta,
        'avg_factual': avg_factual,
        'avg_natural': avg_natural,
        'avg_total': avg_total,
        'pct_improved': pct_improved,
        'high_factual_count': high_factual,
        'pct_high_factual': pct_high_factual
    }

def print_summary_table(summaries: List[Dict]):
    """Print a formatted summary table."""
    # Sort by total score
    summaries.sort(key=lambda x: x['avg_total'], reverse=True)

    print("\n" + "="*100)
    print("KEYWORD OPTIMIZATION TEST SUMMARY")
    print("="*100)

    header = f"{'Approach':<20} {'Tests':>6} {'Baseline':>9} {'Optimized':>10} {'Delta':>8} {'Factual':>9} {'Natural':>9} {'Total':>8} {'%Hi-Fact':>10}"
    print(header)
    print("-"*100)

    for s in summaries:
        row = (
            f"{s['name']:<20} "
            f"{s['n']:>6} "
            f"{s['avg_baseline_kw']:>9.2f} "
            f"{s['avg_optimized_kw']:>10.2f} "
            f"{s['avg_kw_delta']:>+8.2f} "
            f"{s['avg_factual']:>9.2f} "
            f"{s['avg_natural']:>9.2f} "
            f"{s['avg_total']:>8.2f} "
            f"{s['pct_high_factual']:>9.1f}%"
        )
        print(row)

    print("="*100)
    print("\nColumn definitions:")
    print("  Baseline:   Avg keyword score before optimization (1-10)")
    print("  Optimized:  Avg keyword score after optimization (1-10)")
    print("  Delta:      Change in keyword score (+/-)")
    print("  Factual:    Avg factual preservation score (1-10, higher = better)")
    print("  Natural:    Avg natural flow score (1-10)")
    print("  Total:      Weighted total score (0-100)")
    print("  %Hi-Fact:   % of bullets with factual score >= 8")

    # Winner
    if summaries:
        winner = summaries[0]
        print(f"\n🏆 WINNER: {winner['name']}")
        print(f"   Total Score: {winner['avg_total']:.2f}/100")
        print(f"   Keyword Improvement: {winner['avg_kw_delta']:+.2f} points")
        print(f"   Factual Accuracy: {winner['avg_factual']:.2f}/10 ({winner['pct_high_factual']:.1f}% high)")
        print()

def main():
    # Load both result sets
    print("\n📊 Loading test results...")

    # First test (9 approaches)
    try:
        keyword_data = load_results('keyword_results.json')
        keyword_approaches = keyword_data.get('approaches', {})
        print(f"✓ Loaded keyword_results.json: {len(keyword_approaches)} approaches")
    except FileNotFoundError:
        keyword_approaches = {}
        print("⚠ keyword_results.json not found")

    # Second test (3 new approaches)
    try:
        new_data = load_results('new_approaches_results.json')
        print(f"✓ Loaded new_approaches_results.json: {len(new_data)} approaches")
    except FileNotFoundError:
        new_data = {}
        print("⚠ new_approaches_results.json not found")

    # Combine all approaches
    all_summaries = []

    # Process original approaches
    for approach_name, approach_data in keyword_approaches.items():
        results = approach_data.get('results', [])
        summary = summarize_approach(approach_name, results)
        if summary:
            all_summaries.append(summary)

    # Process new approaches (different format)
    for approach_name, results in new_data.items():
        # Need to convert to the expected format
        converted_results = []
        for r in results:
            if 'factual' in r and 'keyword' in r:
                # Simulate the expected format
                converted_results.append({
                    'baseline_keyword_score': 5,  # Unknown baseline
                    'keyword_delta': r['keyword'] - 5,  # Assuming baseline of 5
                    'optimized_scores': {
                        'keyword_alignment': r['keyword'],
                        'factual_preservation': r['factual'],
                        'natural_flow': 7,  # Not measured in new test
                        'ats_improvement': 7,  # Not measured
                        'total': r['factual'] * 0.3 + r['keyword'] * 0.4 + 7 * 0.3  # Approximate
                    }
                })

        summary = summarize_approach(approach_name, converted_results)
        if summary:
            summary['name'] = f"{approach_name} (NEW)"
            all_summaries.append(summary)

    # Print combined summary
    print_summary_table(all_summaries)

    # Show prompts used
    print("\n📝 PROMPT APPROACHES TESTED:\n")

    print("FIRST TEST (Full evaluation with 4 dimensions):")
    print("  1. simple         - Conservative synonym swapping only")
    print("  2. targeted       - Extract JD keywords, then inject")
    print("  3. aggressive     - Maximize keyword density")
    print("  4. with_context   - Uses stored facts for keyword context")
    print("  5. hybrid         - Multi-candidate selection")
    print("  6. factual_first  - Facts first, minimal changes only")
    print("  7. synonym_only   - ONLY 1:1 synonym swaps")
    print("  8. light_touch    - Small adjustments with guardrails")
    print("  9. one_change     - Exactly ONE safe keyword change")

    print("\nSECOND TEST (Simplified 2-dimension scoring):")
    print("  1. synonym_only (NEW)  - Re-tested with stricter prompt")
    print("  2. light_touch (NEW)   - Re-tested with stricter prompt")
    print("  3. one_change (NEW)    - Re-tested with stricter prompt")

    print("\n" + "="*100)

if __name__ == "__main__":
    main()
