from typing import Optional
from .config import REPROMPT_TRIES, CHAT_MODEL, client, log

def tiered_char_cap(orig_len: int, override: Optional[int] = None) -> int:
    if override and override > 0: return override
    if orig_len <= 110: return 100
    if orig_len <= 210: return 200
    return 300

def enforce_char_cap_with_reprompt(cur: str, cap: int) -> str:
    text = (cur or "").replace("\n", " ").strip().lstrip("-• ").strip()
    if not client: return text[:cap].rstrip()
    if len(text) <= cap: return text
    for t in range(REPROMPT_TRIES):
        prompt = (
            f"Rewrite this resume bullet in {cap} characters or fewer. "
            "Preserve numbers and the core result. One concise clause. No filler. "
            "Return only the bullet text, no dash, no quotes.\n\n"
            f"Bullet:\n{text}"
        )
        r = client.chat.completions.create(model=CHAT_MODEL, messages=[{"role":"user","content":prompt}], temperature=0)
        nxt = (r.choices[0].message.content or "").replace("\n", " ").strip().lstrip("-• ").strip()
        log.info(f"reprompt try={t+1} cap={cap} prev_len={len(text)} new_len={len(nxt)}")
        text = nxt
        if len(text) <= cap: break
    if len(text) > cap:
        log.info(f"truncate len={len(text)} -> cap={cap}")
        text = text[:cap].rstrip()
    return text