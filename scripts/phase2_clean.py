#!/usr/bin/env python3
"""Canonical Phase 2 cleaning script — run daily by the news pipeline.

Usage:
    python3 scripts/phase2_clean.py <TODAY>   # e.g. 2026-09-25

Does: SEO farm removal, URL normalization, dedup (URL + title similarity),
interest flagging. Writes data/<TODAY>/cleaned_items.json and health_report.json.
Health report is derived from manifest.json + fetch.log (no hardcoded values).

This script is a permanent repo file. Do NOT write a new dated copy each day —
just run this one. If the cleaning logic needs changes, edit THIS file.
"""
import json, re, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

SCRIPT_DIR = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2:
    print("usage: phase2_clean.py <YYYY-MM-DD>"); sys.exit(1)
TODAY = sys.argv[1]
DATA = SCRIPT_DIR / 'data' / TODAY

items = json.load(open(DATA / 'raw_items.json'))
print(f"Starting with {len(items)} items")

# --- SEO farm detection ---
seo_domains = [r'.*\.com\.pk$', r'.*\.com\.ng$', r'content-services-domain\..*', r'article-cube\..*']
seo_patterns = [re.compile(p, re.I) for p in seo_domains]

def is_seo_farm(url):
    if not url: return False
    domain = urlparse(url).netloc.lower()
    return any(pat.match(domain) for pat in seo_patterns)

# --- URL normalization ---
def normalize_url(url):
    if not url: return ""
    url = url.split('#')[0]
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in params.items()
                    if not k.lower().startswith('utm_')
                    and k.lower() not in ('ref', 'source', 'mc_cid', 'mc_eid', '_ga', 'si', 'spm',
                                          'at_medium', 'at_campaign')}
    new_query = urlencode(clean_params, doseq=True)
    clean_url = parsed._replace(query=new_query).geturl()
    if clean_url.endswith('/') and parsed.path != '/':
        clean_url = clean_url.rstrip('/')
    return clean_url.lower()

def title_similarity(t1, t2):
    if not t1 or not t2: return 0
    w1 = set(re.findall(r'\w+', t1.lower()))
    w2 = set(re.findall(r'\w+', t2.lower()))
    if not w1 or not w2: return 0
    return len(w1.intersection(w2)) / len(w1.union(w2))

seen_urls = {}
seen_titles = []
duplicates = []
seo_farm_items = []
cleaned = []

for item in items:
    url = item.get('url', '')
    title = item.get('title', '')
    if is_seo_farm(url):
        seo_farm_items.append(item); continue
    norm_url = normalize_url(url)
    if norm_url and norm_url in seen_urls:
        duplicates.append({'title': title, 'url': url, 'duplicate_of': seen_urls[norm_url]})
        continue
    is_dup = False
    for prev_title, prev_idx in seen_titles:
        sim = title_similarity(title, prev_title)
        if sim > 0.8:
            duplicates.append({'title': title, 'url': url, 'duplicate_of_title': prev_title, 'similarity': round(sim, 3)})
            is_dup = True; break
    if is_dup: continue
    cleaned_item = dict(item)
    if norm_url:
        cleaned_item['normalized_url'] = norm_url
        seen_urls[norm_url] = title
    seen_titles.append((title, len(cleaned)))
    cleaned.append(cleaned_item)

print(f"SEO farm removed: {len(seo_farm_items)}")
print(f"Duplicates removed: {len(duplicates)}")
print(f"Cleaned items: {len(cleaned)}")

# --- Interest flagging ---
interest_keywords = {
    'ai_agent': ['agent', 'agentic', 'autonomous', 'orchestrat', 'crew', 'autogen', 'langgraph', 'multi-agent'],
    'llm': ['llm', 'gpt', 'claude', 'gemini', 'llama', 'mistral', 'deepseek', 'benchmark', 'fine-tun', 'fine tun', 'rlhf', 'transformer'],
    'ai_engineering': ['rag', 'eval', 'prompt', 'vector', 'embedding', 'langchain', 'tool use', 'function call', 'mcp'],
    'startup': ['startup', 'funding', 'seed', 'series a', 'series b', 'launch', 'founder', 'yc', 'y combinator'],
    'open_source': ['open source', 'opensource', 'license', 'mit license', 'apache', 'gpl', 'fork'],
    'fullstack': ['framework', 'react', 'vue', 'svelte', 'nextjs', 'next.js', 'deno', 'bun', 'tailwind', 'database', 'postgres', 'redis'],
    'linux': ['linux', 'kernel', 'driver', 'filesystem', 'btrfs', 'ext4', 'systemd'],
    'hardware': ['gpu', 'nvidia', 'amd', 'chip', 'accelerator', 'semiconductor', 'tpu', 'silicon', 'blackwell', 'epyc'],
    'security': ['breach', 'cve', 'vulnerab', 'exploit', 'ransomware', 'privacy', 'zero-day', '0day', 'sandworm', 'botnet'],
    'devtools': ['ide', 'vscode', 'ci/cd', 'github actions', 'docker', 'kubernetes', 'k8s', 'cloud', 'api'],
    'tech_business': ['acqui', 'ipo', 'earnings', 'layoff', 'antitrust', 'meta', 'google', 'apple', 'microsoft', 'amazon', 'openai', 'anthropic'],
    'india_tech': ['india', 'bangalore', 'bengaluru', 'indian'],
}

for item in cleaned:
    text = (item.get('title', '') + ' ' + (item.get('summary') or '') + ' ' + str(item.get('body_text') or item.get('discussion_body') or '')[:500]).lower()
    matched = []
    for category, kws in interest_keywords.items():
        if any(kw in text for kw in kws):
            matched.append(category)
    item['interest_flags'] = list(set(matched))
    score = item.get('score', 0) or 0
    comments = item.get('comments', 0) or item.get('num_comments', 0) or 0
    item['viral_flag'] = bool(score >= 100 or comments >= 50)

json.dump(cleaned, open(DATA / 'cleaned_items.json', 'w'), indent=2)

# --- Health report from actual manifest/fetch.log ---
try:
    manifest = json.load(open(DATA / 'manifest.json'))
except FileNotFoundError:
    manifest = {"sources_fetched": None, "sources_ok": None, "sources_failed": None,
                "failed_sources": [], "note": "manifest.json missing — fetch was killed before writing it"}
failed_sources = []
fetch_log = (DATA / 'fetch.log')
if fetch_log.exists():
    for line in fetch_log.read_text().splitlines():
        if 'ERROR' in line:
            parts = [p.strip() for p in line.split('|')]
            if parts:
                failed_sources.append(parts[0])

health = {
    'date': TODAY,
    'sources_fetched': manifest.get('sources_fetched'),
    'sources_ok': manifest.get('sources_ok'),
    'sources_failed': manifest.get('sources_failed'),
    'failed_sources': failed_sources or manifest.get('failed_sources', []),
    'total_raw_items': len(items),
    'seo_farm_removed': len(seo_farm_items),
    'duplicates_removed': len(duplicates),
    'cleaned_items': len(cleaned),
    'status': 'ok'
}
if manifest.get('note'):
    health['note'] = manifest['note']
json.dump(health, open(DATA / 'health_report.json', 'w'), indent=2)
print('Wrote cleaned_items.json and health_report.json')
