"""Similarity string caching layer to bypass LLM on duplicate static queries."""

import json
from pathlib import Path
from difflib import SequenceMatcher
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

CACHE_FILE = DATA_DIR / "query_cache.json"
CACHE_THRESHOLD = 0.90  # 90% string similarity required for a match

def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(cache_data: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        pass

def normalize_query(query: str) -> str:
    """Normalize query for comparison."""
    import string
    query = query.lower().strip()
    return query.translate(str.maketrans('', '', string.punctuation))

def check_cache(query: str) -> Optional[str]:
    """Check if a highly similar query exists in the cache."""
    cache_data = load_cache()
    if not cache_data:
        return None
        
    norm_query = normalize_query(query)
    best_match = None
    best_score = 0.0
    
    for cached_query, response in cache_data.items():
        norm_cached = normalize_query(cached_query)
        score = SequenceMatcher(None, norm_query, norm_cached).ratio()
        if score > best_score:
            best_score = score
            best_match = response
            
    if best_score >= CACHE_THRESHOLD:
        return best_match
        
    return None

def store_in_cache(query: str, response: str) -> None:
    """Store a successful query and its final text response."""
    cache_data = load_cache()
    cache_data[query] = response
    
    # Simple eviction: keep only last 100 queries
    if len(cache_data) > 100:
        oldest_key = next(iter(cache_data))
        del cache_data[oldest_key]
        
    save_cache(cache_data)
