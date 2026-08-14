# Morning News Pipeline

An AI agent that doomscrolls X, Reddit, HackerNews, and 600+ RSS feeds, filters hype from substance, and hands you a briefing with a podcast episode — every morning at 4 AM.

## How it works

A 7-stage pipeline runs daily on a [Hermes Agent](https://hermes-agent.nousresearch.com) instance:

```
4:00 AM  Phase 1   Fetch (script, 0 tokens)
         │         RSS (54 feeds) · HN API · Google News · Reddit (29 subs) · X (118 accounts) · GitHub trending
         ▼
4:45 AM  Phase 2   Verify & Clean (lightweight model)
         │         Retry failed sources · SEO farm detection · Same-day dedup
         ▼
4:50 AM  Phase 3-5 Process (frontier model — the filter)
         │         Hype assessment · Chapter assignment · STE100 summaries · Discussion TLDRs
         ▼
5:15 AM  Phase 5.5 Free-Roam (frontier model)
         │         Cross-reference stories · Fill gaps · Cross-session dedup (7-day memory)
         │         Verifies if a story is new, an update, or a duplicate
         ▼
5:40 AM  Phase 6   Deliver (frontier model)
         │         DeArrow-style headlines · Telegram message · Writes delivery history
         ▼
On-demand Phase 7  Podcast
                   NotebookLM audio overview · ~24 min · Sent as Telegram voice bubble
```

### The filter

The pipeline fetches ~700-800 raw items daily. After dedup and filtering, ~40-60 make it to the briefing. That's an 88-92% drop rate.

Every item gets one of four classifications:

- 🔥 **hype-worthy** — trending AND substantive
- 📊 **substance** — real news, not necessarily viral
- 💤 **hype** — trending but no substance
- ↻ **update** — new development on a story from the past 7 days

### Cross-session dedup

Stories that stay viral across multiple days don't repeat as fresh news. The pipeline keeps a 7-day history of delivered items. Phase 5.5 reads this history and marks each item as new, update, or duplicate.

### STE100 summaries

Every item is summarized in [ASD-STE100 Simplified Technical English](https://www.asd-ste100.org/) — an aerospace writing standard. Short sentences. Active voice. One idea per sentence. No ambiguity.

## Architecture

See [DESIGN.md](DESIGN.md) for the full architecture document — phase breakdown, token budgets, data flow, and design decisions.

## Setup

### Dependencies

| Component | Purpose |
|---|---|
| [Hermes Agent](https://hermes-agent.nousresearch.com) | Runs the pipeline via cron |
| Python 3.11+ | Fetch script |
| `feedparser` | RSS/Atom parsing |
| `twscrape` | X timeline scraping |
| `notebooklm-py` | Podcast generation via Google NotebookLM |
| [Camofox](https://github.com/nicepkg/camofox) | Browser automation (Reddit, GitHub trending) |
| `ffmpeg` | Audio conversion (MP3 → OGG for Telegram) |

### Configuration

1. **Sources** — edit `sources.yaml` to define your RSS feeds, Reddit subreddits, X accounts, and Google News queries
2. **Interests** — edit `interests.yaml.md` to set what the pipeline prioritizes (AI, startups, open source, etc.)
3. **X accounts** — edit `x_accounts.txt` (one username per line)
4. **Cron** — schedule the pipeline to run daily (see DESIGN.md for cron config)

### Running

The fetch script runs as a no-agent cron job. The remaining phases run as a single Hermes Agent session that reads each phase prompt from `prompts/` sequentially.

```bash
# Phase 1 — fetch (script, no LLM)
python3 scripts/fetch.py

# Phases 2-6 — agent reads prompts sequentially
# Phase 7 — on-demand when you reply /podcast to the briefing
```

## File structure

```
├── DESIGN.md                  Architecture document
├── sources.yaml               Source definitions (RSS, Reddit, X, HN, Google News)
├── interests.yaml.md          Interest profile for scoring
├── x_accounts.txt             X accounts to scrape
├── prompts/
│   ├── phase2-verify.md       Verify & clean (dedup, SEO, retries)
│   ├── phase3-5-process.md    Process (hype, chapters, summaries, TLDRs)
│   ├── phase5.5-freeroam.md   Free-roam + cross-session dedup
│   ├── phase6-deliver.md      Telegram delivery + history write
│   └── phase7-podcast.md      NotebookLM podcast generation
├── scripts/
│   ├── fetch.py               Phase 1 fetch script
│   └── phase2_clean.py        Phase 2 mechanical dedup/clean
└── spikes/
    └── old-reddit-eval/       Spike: old.reddit.com scraping validation
```

## License

MIT
