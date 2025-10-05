from typing import Dict
from .config import USE_DISTILLED_JD, W_DISTILLED, W_EMB, W_KEY, W_LLM
from .llm_utils import embed, llm_fit_score, llm_distill_jd, llm_extract_terms
from .text_utils import keyword_coverage, weighted_keyword_coverage

def cosine(a, b):
    if not a or not b: return 0.0
    s = sum(x*y for x, y in zip(a, b))
    na = sum(x*x for x in a) ** 0.5
    nb = sum(y*y for y in b) ** 0.5
    if na == 0 or nb == 0: return 0.0
    return s / (na * nb)

def composite_score(resume_text: str, jd_text: str) -> Dict:
    jd_for_terms = jd_text
    jd_for_embed = jd_text
    if USE_DISTILLED_JD:
        distilled = llm_distill_jd(jd_text)
        jd_for_embed = distilled
    else:
        distilled = None

    emb_r = embed(resume_text)
    emb_j_dist = embed(jd_for_embed)
    sim_dist = cosine(emb_r, emb_j_dist)
    sim_orig = cosine(emb_r, embed(jd_text)) if USE_DISTILLED_JD else sim_dist
    semantic = W_DISTILLED * sim_dist + (1.0 - W_DISTILLED) * sim_orig

    if distilled is not None:
        jd_for_terms = distilled
        terms = llm_extract_terms(jd_for_terms)
        key = weighted_keyword_coverage(resume_text, terms)
    else:
        key = keyword_coverage(resume_text, jd_text)

    llm = llm_fit_score(resume_text, jd_for_terms) / 100.0
    score = W_EMB*semantic + W_KEY*key + W_LLM*llm
    return {
        "embed_sim": round(semantic, 4),
        "keyword_cov": round(key, 4),
        "llm_score": round(llm*100.0, 1),
        "composite": round(score*100.0, 1),
        "distilled_used": bool(distilled is not None),
        "llm_terms_used": bool(distilled is not None),
    }