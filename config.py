import os, sys, logging
from anthropic import Anthropic
from openai import OpenAI
from supabase import create_client, Client

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("resume")
log.propagate = True

# --- Anthropic (for chat completions) ---
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
client = Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None
CHAT_MODEL = os.getenv("CHAT_MODEL", "claude-sonnet-4-5-20250929")

# --- OpenAI (for embeddings only) ---
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

# --- Supabase ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("Supabase client initialized successfully")
    except Exception as e:
        log.warning(f"Failed to initialize Supabase client: {e}")
        supabase = None
else:
    log.warning("Supabase credentials not found. Q&A features will be disabled.")

# --- Feature toggles ---
USE_LLM_TERMS = os.getenv("USE_LLM_TERMS", "1") == "1"
USE_DISTILLED_JD = os.getenv("USE_DISTILLED_JD", "1") == "1"
W_DISTILLED = float(os.getenv("W_DISTILLED", "0.7"))

# --- Caps and retries ---
REPROMPT_TRIES = int(os.getenv("REPROMPT_TRIES", "3"))

# --- Scoring weights ---
W_EMB = float(os.getenv("W_EMB", "0.4"))
W_KEY = float(os.getenv("W_KEY", "0.2"))
W_LLM = float(os.getenv("W_LLM", "0.4"))

# --- Bullet chars ---
BULLET_CHARS = {"•","·","-","–","—","◦","●","*"}

def health():
    return {
        "status": "ok",
        "anthropic": bool(ANTHROPIC_KEY),
        "openai_embeddings": bool(OPENAI_KEY),
        "supabase": bool(supabase),
        "models": {"embed": EMBED_MODEL, "chat": CHAT_MODEL},
        "weights": {"emb": W_EMB, "keywords": W_KEY, "llm": W_LLM, "semantic_distilled_weight": W_DISTILLED},
        "features": {"use_llm_terms": USE_LLM_TERMS, "use_distilled_jd": USE_DISTILLED_JD},
        "reprompt_tries": REPROMPT_TRIES,
    }