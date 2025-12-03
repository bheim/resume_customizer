#!/usr/bin/env python3
"""
Iterative Prompt Optimization Script

Uses LLM-as-optimizer to suggest improvements to prompts based on evaluation results.

Usage:
    # Run baseline evaluation first
    python evaluate_prompts.py --save baseline_results.json

    # Then optimize
    python optimize_prompts.py baseline_results.json

    # This will suggest improvements for WITH-FACTS and NO-FACTS prompts
"""

import json
import sys
import argparse
from typing import Dict, List, Any
from config import client, CHAT_MODEL, log


def analyze_results(results_data: Dict) -> Dict[str, Any]:
    """Analyze evaluation results to identify patterns and issues."""

    results = results_data['results']

    # Separate by context type
    with_context = [r for r in results if r['has_context']]
    without_context = [r for r in results if not r['has_context']]

    # Find common issues
    all_issues = []
    for r in results:
        all_issues.extend(r['scores'].get('issues', []))

    # Count issue frequency
    issue_counts = {}
    for issue in all_issues:
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    # Dimension weaknesses
    dimensions = ['relevance', 'conciseness', 'impact', 'action_verbs', 'factual_accuracy', 'keyword_alignment']
    dim_scores = {d: [] for d in dimensions}

    for r in results:
        for dim in dimensions:
            dim_scores[dim].append(r['scores'].get(dim, 0))

    dim_averages = {d: sum(scores) / len(scores) if scores else 0 for d, scores in dim_scores.items()}

    # Identify lowest performing dimensions (< 6.5)
    weak_dimensions = {d: score for d, score in dim_averages.items() if score < 6.5}

    return {
        'total_tests': len(results),
        'avg_score_with_context': sum(r['scores'].get('total', 0) for r in with_context) / len(with_context) if with_context else 0,
        'avg_score_without_context': sum(r['scores'].get('total', 0) for r in without_context) / len(without_context) if without_context else 0,
        'common_issues': sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        'weak_dimensions': weak_dimensions,
        'dimension_averages': dim_averages,
        'worst_cases': sorted(results, key=lambda x: x['scores'].get('total', 0))[:5],
        'with_context_results': with_context,
        'without_context_results': without_context
    }


def get_current_prompts() -> Dict[str, str]:
    """Extract current prompts from llm_utils.py"""

    # Read the file
    with open('llm_utils.py', 'r') as f:
        content = f.read()

    # Extract WITH-FACTS prompt (between specific markers)
    with_facts_start = content.find('prompt = f"""You are a professional resume writer creating a new, optimized bullet point.')
    with_facts_end = content.find('Return ONLY the new bullet."""', with_facts_start)

    # Extract NO-FACTS prompt
    no_facts_start = content.find('prompt = f"""You are a professional resume writer. Optimize this bullet')
    no_facts_end = content.find('Return ONLY the optimized bullet text. No explanations, no commentary."""', no_facts_start)

    with_facts_prompt = content[with_facts_start:with_facts_end + len('Return ONLY the new bullet."""')] if with_facts_start != -1 else "NOT FOUND"
    no_facts_prompt = content[no_facts_start:no_facts_end + len('Return ONLY the optimized bullet text. No explanations, no commentary."""')] if no_facts_start != -1 else "NOT FOUND"

    return {
        'with_facts': with_facts_prompt,
        'no_facts': no_facts_prompt
    }


def llm_suggest_improvements(
    prompt_type: str,  # "with_facts" or "no_facts"
    current_prompt: str,
    analysis: Dict[str, Any]
) -> str:
    """Use LLM to suggest prompt improvements based on evaluation analysis."""

    if prompt_type == "with_facts":
        context = "WITH-FACTS path (uses stored context about accomplishments)"
        relevant_results = analysis['with_context_results']
        avg_score = analysis['avg_score_with_context']
    else:
        context = "NO-FACTS path (conservative optimization without context - must avoid hallucination)"
        relevant_results = analysis['without_context_results']
        avg_score = analysis['avg_score_without_context']

    # Get specific examples of issues
    low_scoring = [r for r in relevant_results if r['scores'].get('total', 0) < 6.5]
    example_issues = []
    for r in low_scoring[:3]:
        example_issues.append({
            'original': r['original'],
            'optimized': r['optimized'],
            'score': r['scores'].get('total', 0),
            'issues': r['scores'].get('issues', [])
        })

    system_prompt = f"""You are an expert prompt engineer. Your task is to improve a resume bullet optimization prompt based on evaluation results.

CONTEXT: This is the {context}
CURRENT AVERAGE SCORE: {avg_score:.1f}/10

IDENTIFIED WEAKNESSES:
"""

    # Add weak dimensions
    for dim, score in analysis['weak_dimensions'].items():
        system_prompt += f"- {dim}: {score:.1f}/10 (needs improvement)\n"

    # Add common issues
    system_prompt += "\nMOST COMMON ISSUES:\n"
    for issue, count in analysis['common_issues'][:5]:
        system_prompt += f"- {issue} (occurred {count} times)\n"

    # Add examples
    if example_issues:
        system_prompt += "\nEXAMPLE FAILURES:\n"
        for ex in example_issues:
            system_prompt += f"\nScore: {ex['score']}/10\n"
            system_prompt += f"Original: {ex['original']}\n"
            system_prompt += f"Optimized: {ex['optimized']}\n"
            system_prompt += f"Issues: {', '.join(ex['issues'])}\n"

    system_prompt += f"""

CURRENT PROMPT:
{current_prompt}

---

YOUR TASK:
Analyze the current prompt and suggest specific improvements to address the identified weaknesses.

GUIDELINES:
1. Keep the overall structure and key principles
2. Add specific, actionable guidance to fix the weak dimensions
3. Include concrete examples where helpful
4. Make instructions more precise and harder to misinterpret
5. For NO-FACTS: strengthen anti-hallucination language
6. For WITH-FACTS: improve conciseness and ending strength

RETURN FORMAT:
Provide the improved prompt in full, ready to be copy-pasted into the code.
Also include a brief explanation of key changes made.

Format your response as:

<IMPROVED_PROMPT>
[full improved prompt here]
</IMPROVED_PROMPT>

<EXPLANATION>
Key changes made:
1. [change 1]
2. [change 2]
3. [change 3]
</EXPLANATION>
"""

    try:
        r = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.3  # Slight creativity for improvements
        )

        return (r.choices[0].message.content or "").strip()

    except Exception as e:
        log.exception(f"Error getting LLM suggestions: {e}")
        return f"ERROR: {str(e)}"


def main():
    parser = argparse.ArgumentParser(description='Optimize prompts based on evaluation results')
    parser.add_argument('results_file', help='Path to evaluation results JSON')
    parser.add_argument('--prompt-type', choices=['with_facts', 'no_facts', 'both'], default='both',
                        help='Which prompt to optimize')

    args = parser.parse_args()

    print(f"\n{'='*80}")
    print("PROMPT OPTIMIZATION - Using LLM to Improve Prompts")
    print(f"{'='*80}\n")

    # Load evaluation results
    with open(args.results_file, 'r') as f:
        results_data = json.load(f)

    print(f"Loaded {results_data['total_tests']} test results from {args.results_file}\n")

    # Analyze results
    print("Analyzing results to identify improvement areas...")
    analysis = analyze_results(results_data)

    print(f"\nCurrent Performance:")
    print(f"  WITH Context:    {analysis['avg_score_with_context']:.1f}/10")
    print(f"  WITHOUT Context: {analysis['avg_score_without_context']:.1f}/10")

    print(f"\nWeak Dimensions:")
    for dim, score in analysis['weak_dimensions'].items():
        print(f"  {dim}: {score:.1f}/10")

    print(f"\nTop Issues:")
    for issue, count in analysis['common_issues'][:5]:
        print(f"  {count}x: {issue}")

    # Get current prompts
    print(f"\nExtracting current prompts from llm_utils.py...")
    current_prompts = get_current_prompts()

    # Generate suggestions
    prompt_types = ['with_facts', 'no_facts'] if args.prompt_type == 'both' else [args.prompt_type]

    for prompt_type in prompt_types:
        print(f"\n{'='*80}")
        print(f"OPTIMIZING: {prompt_type.upper().replace('_', '-')} PROMPT")
        print(f"{'='*80}\n")

        print("Asking LLM for improvement suggestions...")

        suggestions = llm_suggest_improvements(
            prompt_type,
            current_prompts[prompt_type],
            analysis
        )

        # Save suggestions to file
        output_file = f"prompt_suggestions_{prompt_type}.txt"
        with open(output_file, 'w') as f:
            f.write(suggestions)

        print(f"\n✅ Suggestions saved to: {output_file}")
        print(f"\nPreview:")
        print("-" * 80)
        print(suggestions[:500])
        print("...")
        print("-" * 80)

    print(f"\n{'='*80}")
    print("NEXT STEPS:")
    print("1. Review the suggestions in prompt_suggestions_*.txt")
    print("2. Update prompts in llm_utils.py")
    print("3. Run: python evaluate_prompts.py --save improved_results.json")
    print("4. Compare: diff baseline_results.json improved_results.json")
    print("5. If improved, commit changes. If not, iterate!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python optimize_prompts.py <results_file.json>")
        print("\nExample workflow:")
        print("  1. python evaluate_prompts.py --save baseline_results.json")
        print("  2. python optimize_prompts.py baseline_results.json")
        print("  3. Update prompts in llm_utils.py based on suggestions")
        print("  4. python evaluate_prompts.py --save improved_results.json")
        sys.exit(1)

    main()
