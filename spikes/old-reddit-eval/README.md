# Spike: old.reddit.com vs new Reddit

## Verdict: VALIDATED ✅

### Spike Results

| # | Spike | Result |
|---|-------|--------|
| 001 | Post listing | ✅ 25 posts extracted with scores/comments/titles/URLs |
| 002 | Comment extraction + rate limit | ✅ **125/125 pages, 0 failures, NO rate limiting, 4.2 min** |
| 003 | Login persistence | ✅ MitransClaw session persists (karma, vote arrows, mail) |
| 004 | Score parsing | ✅ "17.0k" → 17000, "814 comments" → 814 |

### What worked
- old.reddit.com serves static HTML — no async web components
- 125 consecutive comment pages with ZERO failures (new Reddit failed at 29)
- Login session from new Reddit persists to old.reddit.com
- 200 comments available instantly on each page (vs 0-10 on new Reddit after rate limit)
- Faster: 1.5s per page vs 4-8s on new Reddit
- Simpler DOM: `.thing.link`, `.md`, `.score.unvoted` — no custom elements

### What didn't
- Nothing. All spikes passed.

### Implementation changes
- REDDIT_JS: `shreddit-post` → `.thing.link` + `a.title` + `.score.unvoted` + `a.comments`
- REDDIT_COMMENTS_JS: `shreddit-comment` → `.comment` + `.md` + `.score.unvoted`
- Added `parse_reddit_score()` and `parse_reddit_comments()` for text → int conversion
- URLs: `www.reddit.com` → `old.reddit.com`
- Removed tab rotation (not needed)
- Removed retry loop (comments load instantly on static HTML)
- Wait times: 4s → 1.5s (post listing), 4s+3s×3 → 1.5s (comments)
- Pacing: 1s → 0.5s

### Time savings
- Post listing: 29 subs × 2s saved = 58s
- Comment extraction: 68 posts × 2.5s saved = 170s
- Tab rotation: removed entirely = ~12s saved
- Total: ~4 minutes faster per run
