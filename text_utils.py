import re
from collections import Counter
from typing import List, Dict

STOPWORDS = set("""
a an the and or for of to in on at by with from as is are was were be been being
this that these those such into across over under within without not no nor than
your you we they he she it their our us
""".split())
TOKEN_RE = re.compile(r"[A-Za-z0-9+#\-\.]+")

def simple_tokens(text: str) -> List[str]:
    toks = [t.lower() for t in TOKEN_RE.findall(text)]
    return [t for t in toks if len(t) > 1 and t not in STOPWORDS]

def keyword_set(text: str) -> set:
    toks = simple_tokens(text)
    return set([t for t in toks if any(c.isalpha() for c in t) and len(t) >= 3])

def keyword_coverage(resume_text: str, jd_text: str) -> float:
    rset = keyword_set(resume_text)
    jset = keyword_set(jd_text)
    if not jset: return 0.0
    hits = len(jset & rset)
    return hits / len(jset)

def weighted_keyword_coverage(resume_text: str, jd_terms: Dict[str, List[str]]) -> float:
    weights = {"tools":3, "skills":2, "responsibilities":2, "domains":2, "certifications":1, "seniority":1}
    res_lower = resume_text.lower()
    total_weight = 0; hit_weight = 0
    for cat, terms in jd_terms.items():
        w = weights.get(cat, 1)
        for t in terms:
            t_norm = t.lower().strip()
            if not t_norm: continue
            total_weight += w
            if t_norm in res_lower: hit_weight += w
    if total_weight == 0: return 0.0
    return hit_weight / total_weight

def top_terms(text: str, k: int = 25) -> List[str]:
    toks = [t for t in simple_tokens(text) if any(c.isalpha() for c in t) and len(t) >= 3]
    freq = Counter(toks)
    return [t for t, _ in freq.most_common(k)]