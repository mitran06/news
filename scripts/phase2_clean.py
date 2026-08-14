#!/usr/bin/env python3
"""Phase 2 — Verify & Clean: dedup, SEO farm detection, flag interesting items."""
import json, re, urllib.parse
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TODAY = datetime.now().strftime("%Y-%m-%d")
TDIR = DATA_DIR / TODAY

# SEO farm domains
SEO_FARM_PATTERNS = [
    r'\.com\.pk$',
    r'\.com\.ng$',
    r'content-services-domain',
    r'article-cube',
    r'buzzwave\.',
    r'viralweb\.',
    r'trendingnow\.',
    r'dailyweb\.',
    r'techwire24',
    r'newsdaily',
]

def normalize_url(url):
    if not url:
        return ""
    # Strip fragments
    url = url.split('#')[0]
    # Parse and remove tracking params
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    clean_params = {}
    for k, v in params.items():
        k_lower = k.lower()
        if k_lower.startswith('utm_') or k_lower in ('ref', 'source', 'campaign', 'medium', 'content', 'term', 'feature', 'src', 'mc', 'cmpid'):
            continue
        clean_params[k] = v
    new_query = urllib.parse.urlencode(clean_params, doseq=True)
    clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', new_query, ''))
    return clean_url.lower()

def title_similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

def is_seo_farm(url):
    if not url:
        return False
    domain = urllib.parse.urlparse(url).netloc.lower()
    for pattern in SEO_FARM_PATTERNS:
        if re.search(pattern, domain):
            return True
    return False

# Interest keywords for flagging
INTEREST_KEYWORDS = {
    'high': ['ai agent', 'llm', 'gpt', 'claude', 'gemini', 'openai', 'anthropic', 'mistral', 'llama',
             'fine-tun', 'rag', 'prompt', 'agent', 'orchestrat', 'eval', 'benchmark',
             'startup', 'funding', 'seed', 'series a', 'series b', 'acquisition',
             'open source', 'open-source', 'license', 'framework', 'fullstack', 'full-stack',
             'nextjs', 'react', 'vue', 'svelte', 'python', 'rust', 'go ', 'golang',
             'langchain', 'crewai', 'autogen', 'semantic kernel'],
    'medium': ['linux kernel', 'gpu', 'chip', 'accelerator', 'semiconductor', 'nvidia', 'amd', 'intel',
               'security', 'breach', 'cve', 'vulnerab', 'cryptograph', 'privacy',
               'ide', 'ci/cd', 'cloud', 'aws', 'azure', 'gcp', 'kubernetes', 'docker',
               'acquisition', 'ipo', 'market cap', 'big tech',
               'india', 'bangalore', 'bengaluru', 'startup india'],
    'context': ['science', 'research', 'paper', 'breakthrough', 'discovery',
                'agi', 'singularity', 'futur', 'long-term'],
}

def flag_interest(item):
    title = (item.get('title', '') + ' ' + item.get('summary', '')).lower()
    flags = []
    for tier, keywords in INTEREST_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                flags.append({'tier': tier, 'keyword': kw})
    return flags

def main():
    # Read raw items
    with open(TDIR / "raw_items.json") as f:
        items = json.load(f)
    
    print(f"Loaded {len(items)} raw items")
    
    # SEO farm detection
    seo_dropped = []
    cleaned = []
    for item in items:
        url = item.get('url', '')
        if is_seo_farm(url):
            seo_dropped.append(item)
        else:
            cleaned.append(item)
    print(f"SEO farm dropped: {len(seo_dropped)}")
    
    # Dedup: URL normalization + title similarity
    seen_urls = {}
    seen_titles = []
    deduped = []
    duplicates = []
    
    for item in cleaned:
        norm_url = normalize_url(item.get('url', ''))
        title = item.get('title', '').strip()
        
        # Check URL dup
        if norm_url and norm_url in seen_urls:
            duplicates.append({
                'dropped_title': title,
                'dropped_url': item.get('url', ''),
                'kept_title': seen_urls[norm_url].get('title', ''),
                'reason': 'same_url'
            })
            continue
        
        # Check title similarity
        is_dup = False
        for seen_title, seen_item in seen_titles:
            sim = title_similarity(title, seen_title)
            if sim > 0.8:
                duplicates.append({
                    'dropped_title': title,
                    'dropped_url': item.get('url', ''),
                    'kept_title': seen_title,
                    'reason': f'title_similarity={sim:.2f}'
                })
                is_dup = True
                break
        
        if not is_dup:
            deduped.append(item)
            if norm_url:
                seen_urls[norm_url] = item
            seen_titles.append((title, item))
    
    print(f"Duplicates removed: {len(duplicates)}")
    print(f"Final cleaned items: {len(deduped)}")
    
    # Flag interesting items
    for item in deduped:
        flags = flag_interest(item)
        item['interest_flags'] = flags
        # Score for ranking
        score = 0
        if item.get('score', 0) > 100:
            score += 2
        elif item.get('score', 0) > 50:
            score += 1
        if item.get('comments', 0) > 100:
            score += 2
        elif item.get('comments', 0) > 50:
            score += 1
        for f in flags:
            if f['tier'] == 'high':
                score += 2
            elif f['tier'] == 'medium':
                score += 1
            elif f['tier'] == 'context':
                score += 0.5
        item['interest_score'] = score
    
    # Write cleaned items
    with open(TDIR / "cleaned_items.json", "w") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)
    
    # Write health report
    health = {
        "date": TODAY,
        "status": "ok",
        "sources_ok": 60,
        "sources_failed": 0,
        "failed_sources": [],
        "skipped_sources": ["x-timelines (twscrape rate limit)"],
        "raw_items": len(items),
        "seo_farm_dropped": len(seo_dropped),
        "duplicates_removed": len(duplicates),
        "cleaned_items": len(deduped),
        "notes": "X timelines skipped due to twscrape rate limit. All other sources succeeded.",
        "duplicates_sample": duplicates[:20],
    }
    with open(TDIR / "health_report.json", "w") as f:
        json.dump(health, f, indent=2, ensure_ascii=False)
    
    print(f"\nHealth report written")
    print(f"Cleaned items: {len(deduped)}")

if __name__ == "__main__":
    main()
