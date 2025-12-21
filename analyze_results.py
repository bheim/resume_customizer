import json

# Load results
with open('results_all.json') as f:
    data = json.load(f)

# Leaderboard
print("=" * 70)
print("LEADERBOARD")
print("=" * 70)
stats = []
for name, info in data['approaches'].items():
    results = [r for r in info['results'] if 'deltas' in r]
    if results:
        avg_delta = sum(r['deltas']['total'] for r in results) / len(results)
        avg_score = sum(r['optimized_scores']['total'] for r in results) / len(results)
        stats.append((name, avg_delta, avg_score, len(results)))

stats.sort(key=lambda x: x[1], reverse=True)
for i, (name, delta, score, n) in enumerate(stats, 1):
    print(f"{i}. {name:20} Δ {delta:+.2f}  Score: {score:.2f}")

# Detailed comparison for top 2
print("\n" + "=" * 70)
print("SAMPLE BULLETS - BEST vs WORST APPROACH")
print("=" * 70)

best = stats[0][0]
worst = stats[-1][0]

best_results = data['approaches'][best]['results']
worst_results = data['approaches'][worst]['results']

# Show 3 examples
for i in range(min(3, len(best_results))):
    br = best_results[i]
    wr = worst_results[i]
    
    print(f"\n--- {br['bullet_id']} | {br['jd_type']} ---")
    print(f"ORIGINAL: {br['original'][:100]}...")
    print(f"\n{best.upper()} (Δ {br['deltas']['total']:+.1f}):")
    print(f"  {br['optimized'][:120]}...")
    print(f"  Issues: {br['optimized_scores'].get('issues', [])[:2]}")
    print(f"\n{worst.upper()} (Δ {wr['deltas']['total']:+.1f}):")
    print(f"  {wr['optimized'][:120]}...")
    print(f"  Issues: {wr['optimized_scores'].get('issues', [])[:2]}")

# Dimension breakdown
print("\n" + "=" * 70)
print("DIMENSION BREAKDOWN BY APPROACH")
print("=" * 70)
dims = ['relevance', 'conciseness', 'impact', 'action_verbs', 'factual_accuracy', 'keyword_alignment']

print(f"\n{'Approach':<18}", end="")
for d in dims:
    print(f"{d[:8]:>10}", end="")
print()
print("-" * 78)

for name, info in data['approaches'].items():
    results = [r for r in info['results'] if 'deltas' in r]
    print(f"{name:<18}", end="")
    for d in dims:
        avg = sum(r['deltas'][d] for r in results) / len(results)
        print(f"{avg:>+10.2f}", end="")
    print()

