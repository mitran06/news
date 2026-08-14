# Morning News Pipeline — Design

Daily automated news pipeline. Fetches from multiple sources at 4 AM IST, processes through dedup → filter → score → format, delivers a Telegram briefing at 6 AM IST, and optionally generates a NotebookLM podcast brief on approval.

## Timeline

| Time (IST) | Phase | What runs |
|---|---|---|
| 04:00 | Phase 1 — Fetch | Orchestrator runs fetch script (`timeout 3600 python3 scripts/fetch.py`). ~42 min. |
| ~04:45 | Phase 2 — Verify & Clean | Orchestrator delegates to lightweight model subagent. Dedup, SEO filter, retries. ~5 min. |
| ~04:50 | Phase 3-5 — Process | Orchestrator delegates to frontier subagent. Hype, chapter, summarize, TLDR, deep-dive. ~25 min. |
| ~05:15 | Phase 5.5 — Free-Roam | Orchestrator delegates to frontier subagent. Cross-reference, fill gaps, podcast-source.md. ~25 min. |
| ~05:40 | Phase 6 — Deliver | Orchestrator formats DeArrow headlines and sends Telegram message directly. ~5 min. |

**One cron job, one agent.** The agent runs the fetch script, then executes each phase itself sequentially — no delegation, no subagents. This avoids the the provider's max concurrent request limit. No timing conflicts — each phase waits for the previous to complete. Phase 7 (podcast) is triggered by user reply.

Gateway timeout set to 7200s (2h) to accommodate the full pipeline runtime.

---

## Phase 1 — Collect (Script, no agent)

**Cron:** `0 4 * * *` (4 AM IST), `no_agent=True`, `deliver=local`, `timeout=3600` (60 min).

Expected runtime breakdown:
- RSS feeds (54): ~2 min
- HN API + Google News (4): ~15 sec
- Reddit (29 subs × ~8s): ~4 min
- Reddit comment extraction (all posts ≥50 comments × ~5s each): ~3 min
- GitHub trending: ~10 sec
- X timelines (118 accounts, 3 batches via twscrape, 2× 15min rate limit waits): ~33 min
- X trending: ~10 sec
- **Total: ~42 min** — cron timeout set to 60 min for safety margin.

A bash + Python script that fetches all sources in parallel, stores raw output, and writes a structured log.

### What it does

1. Creates `data/YYYY-MM-DD/` directory.
2. Fetches each source (curl for RSS/API, browser methods for sources that need it).
3. Stores each source's raw output as a separate file: `data/YYYY-MM-DD/<source-name>.json` (or `.xml`).
4. Writes `data/YYYY-MM-DD/fetch.log` with: source name, HTTP status, item count, bytes fetched, errors, timestamp.
5. Writes `data/YYYY-MM-DD/manifest.json` — summary: `{ sources_fetched: N, sources_ok: N, sources_failed: N, total_items: N, failed_sources: [...] }`.

### Source registration

Sources are defined in `sources.yaml` — a single config file the script reads. Each source entry:

```yaml
- name: hn-frontpage
  type: rss          # rss | api | browser
  url: https://hnrss.org/frontpage
  parser: rss        # rss | json | html
  enabled: true

- name: hn-algolia-ai
  type: api
  url: https://hn.algolia.com/api/v1/search?query=AI+agent&tags=story&hitsPerPage=20
  parser: json
  enabled: true
```

Sources are TBD — Mitran will specify exact sources. The script is source-agnostic: add a YAML entry, the script fetches it.

### Log structure

```
[2026-08-10 04:00:01] START fetch
[2026-08-10 04:00:01] FETCH hn-frontpage → 200 OK, 42 items, 128KB
[2026-08-10 04:00:02] FETCH hn-algolia-ai → 200 OK, 20 items, 45KB
[2026-08-10 04:00:03] FETCH google-news-ai → 200 OK, 15 items, 67KB
[2026-08-10 04:00:03] FETCH reddit-r-tech → 403 BLOCKED, 0 items, error
[2026-08-10 04:00:03] SUMMARY: 4 fetched, 3 ok, 1 failed, 77 total items
[2026-08-10 04:00:03] FAILED: [reddit-r-tech]
```

### Completion criterion

All enabled sources fetched, raw data stored, log written, manifest written. Script exits 0 on success even if individual sources fail (failures are logged for Phase 2 to handle).

---

## Phase 2 — Verify & Retry (Agent)

**Cron:** `5 4 * * *` (4:05 AM IST), LLM-driven.

### What it does

1. Read `data/YYYY-MM-DD/fetch.log` and `manifest.json`.
2. For each failed source, attempt a browser-method retry (Playwright via Camofox, or curl with different headers).
3. If retry succeeds, store the data and update the log.
4. If retry still fails, note it in the briefing as "source unavailable today."

### Completion criterion

Every source is either successfully fetched or explicitly marked as failed-after-retry in the log. No silent gaps.

---

## Phase 3 — Filter Hype (Agent)

### What it does

Reads all fetched items, assesses each one: is this substance or hype?

### The _vibe_

The agent acts as a **raw friend** delivering news. Not a corporate analyst. Not a hype machine. A friend who:
- Tells you straight up if something is trending but empty.
- Explains _why_ it's just hype (e.g., "vaporware announcement, no product, no timeline, just a blog post").
- If something is _genuinely_ hype-worthy — like Nvidia cracking a long-standing problem — conveys that energy. "This is actually big, here's why."
- Never tells you how to feel about it. States facts, lets the significance speak.

### Hype assessment criteria

For each item, the agent assigns one of:

- **substance** — real news, real product, real data, real impact.
- **hype** — trending but no substance. The agent says so and explains why.
- **hype-worthy** — trending _and_ substantive. The significance is real. The agent conveys it with appropriate energy.

The filter is not "remove hype." It's "label hype honestly." Hypy items stay in the briefing, clearly marked.

### Completion criterion

All items have a hype assessment with a one-line justification. No item is dropped silently.

---

## Phase 3.5 — Discussion TLDRs (Agent)

### What it does

For items that are discussion threads (high comment count, not just link posts), the agent generates a **TLDR** of the discussion — not the article, the *discussion*. This is inspired by the r/ClaudeAI TLDR bot pattern.

### What gets a TLDR

An item qualifies for a discussion TLDR when:
- It originates from a community source (Reddit, HN, Lobsters) — not a blog/RSS feed.
- It has significant engagement (e.g., >50 comments on Reddit, >100 on HN).
- The discussion itself adds value beyond the headline — i.e., people are debating, sharing experiences, or revealing nuance.

If the post is just a link with no meaningful discussion, no TLDR — the headline + summary from Phase 5 is enough.

### TLDR format

Reverse-engineered from **u/ClaudeAI-mod-bot** ("Wilson"), the moderator bot of r/ClaudeAI (1.7M weekly visitors). The bot generates stickied TLDRs on popular threads at comment milestones (40, 160, 320, 640 comments). Powered by Claude API.

**Format to replicate:**

```
💬 TL;DR of the discussion ([N] comments)

[1-2 sentence opening: state the consensus/verdict with personality and directness. Reference the OP or the core question.]

[1-2 paragraphs: elaborate on the consensus. What does the community agree on? What's the nuance? Include specific quotes or notable points from commenters.]

[Optional bullet list: key highlights, funny moments, or specific takeaways]

[1-2 paragraphs: counterpoints, disagreements, or additional context from the thread]

[Optional: practical takeaways or action items]

[Closing line: punchy, personality-driven summary or verdict]
```

**Style rules (from the actual bot):**
1. **Lead with the verdict** — state the consensus in the first sentence, not the topic.
2. **Be conversational** — casual Reddit tone, not academic summary. Humor and mild sarcasm welcome.
3. **Include specifics** — reference actual quotes, user experiences, and jokes from the thread. Not generic "users discussed X."
4. **Use formatting** — bold for key phrases, bullet lists for breakdowns, `code` for technical terms.
5. **Have personality** — the bot has opinions. The TLDR is not neutral; it takes a stance on what the community actually thinks.
6. **300-600 words** — comprehensive but concise. Cover all major viewpoints.
7. **End with a kicker** — a memorable closing line or practical takeaway.
8. **Acknowledge both sides** — include counterpoints and disagreements, not just the majority view.

**Example (from the real bot, 640 comments):**
> 💬 TL;DR of the discussion (640 comments)
>
> OP dropped a bomb by revealing a simple Google dork (site:claude.ai/share) could pull up thousands of users' shared conversations. The thread immediately went into a full-blown meltdown, with the consensus being that this is a massive privacy breach and a major screw-up by Anthropic.
>
> While a few people argued it's "user error" for sharing links, the overwhelming sentiment is that Anthropic should have used a noindex tag to prevent this...
>
> The thread quickly became a treasure hunt for the most unhinged chats. Highlights include:
> - A user creating a crypto wallet and exposing their keys.
> - A lawyer asking if they need to self-report a breach of conduct.
> - Someone trying to become a nine-tailed fox.
>
> PSA from the comments: You can manage your own shared history under Settings -> Privacy -> Shared Chats. Go check yours. Seriously.

Full research with 3 example TLDRs saved at: `/home/hermes/workspace/claudeai-mod-bot-research.md`

### Completion criterion

Every qualifying discussion item has a TLDR. Non-qualifying items are left to Phase 5 summaries only.

---

## Phase 4 — Order & Chapter (Agent)

### Equal treatment principle

All info is treated equally at ingestion. Ranking, sorting, and filtering happen here — not during fetch. The fetch script collects everything; this phase decides what matters and where it goes.

### What it does

Groups all items into chapters by domain, then orders within each chapter by relevance × impact × importance.

### Chapters

Flexible — defined at runtime based on what's in the news. Default chapters:

- **AI** — models, agents, research, deployments, regulation
- **General Tech** — software, hardware, open source, security
- **Politics** — only if tech-adjacent or globally significant
- **Business** — funding, acquisitions, market moves
- **Science** — breakthroughs, papers, discoveries
- **Cool Shit** — interesting projects, experiments, things people are building, side projects, novel tools. This is the "look at what someone made" section. Not breaking news, not analysis — just cool stuff worth knowing about.

Chapters with no items today are omitted. If a chapter has 1 item, it's still its own section.

### Ordering within chapters

Three-factor sort:
1. **Impact** — how many people/projects does this affect?
2. **Relevance** — how close to Mitran's interests (AI agents, LLMs, Linux/kernel, full-stack dev, open source, dev startups)?
3. **Importance** — is this a one-day story or a long-term shift?

### Completion criterion

All items are in exactly one chapter, ordered, with their hype assessment from Phase 3 and discussion TLDR from Phase 3.5 intact.

---

## Phase 5 — Summarize (Agent)

### What it does

Writes an impactful summary for each item in **ASD-STE100 Simplified Technical English**.

### ASD-STE100 rules (applied to news)

- One idea per sentence.
- Keep sentences short (max ~20 words).
- Use active voice. "Nvidia released..." not "It was released by Nvidia..."
- Use simple verbs. "said" not "stated," "made" not "manufactured," "started" not "commenced."
- No idioms, no metaphors, no jargon unless the jargon is the subject (e.g., "transformer" is fine; "paradigm shift" is not).
- Include enough context that a reader who missed the last week can follow. If a company or term isn't obvious, add a clause: "Mistral, a French AI startup, released..."

### Deep-dives (v2 — model has freedom)

The model can deep-dive any item it finds worth exploring:
- Fetch the linked article (web tools).
- Research the topic for latest context.
- Look up related news.
- Add background info that isn't in the headline.

The model decides what's worth the extra tokens. Most items don't need a deep-dive. But if something is genuinely important, dig in.

### Completion criterion

Every item has a 1–3 sentence STE100 summary with context. Written to `data/YYYY-MM-DD/briefing.md`.

---

## Phase 6 — Telegram Delivery (Agent)

**Cron:** `0 6 * * *` (6 AM IST), LLM-driven.

### What it does

Reads `briefing.md`, formats a Telegram message with DeArrow-style headlines, and sends it.

### DeArrow-inspired headline principles

DeArrow replaces clickbait YouTube titles with descriptive, accurate ones. Applied to news headlines:

- **Descriptive over sensational.** "OpenAI releases GPT-5 with 10x context window" not "OpenAI JUST Changed Everything."
- **No withheld information.** Don't tease. If the headline is "You won't believe what Nvidia just did," that's a failure. Say what Nvidia did.
- **No reaction words.** No "shocking," "mind-blowing," "game-changing." Let the facts carry the energy.
- **Statement over question.** "Apple acquires startup" not "Did Apple just acquire a startup?"
- **Sentence case.** Not Title Case. Not ALL CAPS.
- **Length: enough to inform, not enough to overwhelm.**

### The _friend_ voice (applied to headlines)

The friend voice from Phase 3 carries into the Telegram message. The headlines are DeArrow-clean, but the framing around them can be raw:

> **AI**
>
> 🔥 Nvidia solved a problem that's been stuck for 15 years — real-time path tracing without dedicated hardware. This is the real deal.
>
> Mistral released a 7B model that beats Llama 3 on benchmarks. Good for them, but benchmarks are benchmarks. Wait for real-world usage.
>
> Sam Altman tweeted about AGI again. No product, no timeline, just vibes. Moving on.

The 🔥 / 📊 / 💤 markers indicate hype-worthy / substance / hype. One per item.

### Telegram message structure

```
📰 Morning Briefing — Aug 10

## AI
[marker] DeArrow-style headline
  STE100 summary (1-3 sentences)
  🔗 link

## General Tech
...

## Politics
...

---
🎧 Want a podcast brief? Reply /podcast
```

### Completion criterion

Telegram message sent. `briefing.md` path and `podcast-source.md` path are ready for Phase 7.

---

## Phase 7 — Podcast (Agent, on approval)

### What it does

On `/podcast` reply from Mitran:

1. Read `podcast-source.md` (prepared in Phase 5).
2. Create a NotebookLM notebook with the day's news as a text source.
3. Generate an audio overview (podcast).
4. Download the MP3 and send it as a Telegram voice bubble.

### Podcast source format

`podcast-source.md` is a single text document, chapter by chapter, news by news. Written for NotebookLM's two-host conversational format. Structure:

```markdown
# Morning Briefing — August 10, 2026

## AI

### Nvidia solves real-time path tracing without dedicated hardware
Context: Path tracing is a rendering technique that simulates light rays...
News: Nvidia announced...
Why it matters: This problem has been open since...

### Mistral releases 7B model beating Llama 3
Context: Mistral is a French AI startup...
News: ...

## General Tech
...
```

Each item includes:
- **Context** — what you need to know to follow, even if obvious. A few words.
- **News** — the actual development.
- **Why it matters** — significance, not hype.

### NotebookLM instructions

Written per /writing-for-agents principles. Custom prompt for the audio overview:

The podcast prompt instructs NotebookLM to:
- Go chapter by chapter, news by news.
- Not be boring. Conversational, not lecture-style.
- Provide relevant past context for each item — even if obvious, a few words to get the listener up to speed.
- If something is hype with no substance, say so plainly.
- If something is genuinely big, convey that.
- Not deep-dive. This is a briefing, not a documentary. If the listener wants depth, they'll ask for the link.
- Keep it moving. Don't dwell on one item for too long.

### NotebookLM technical flow

1. Auth via Google cookies from `~/.claw-browser/profiles/mitrans-claw/Default/Cookies` (storage_state extraction — no browser automation needed).
2. `NotebookLMClient` — create notebook, add text source from `podcast-source.md`, submit audio generation.
3. Poll for completion (15-min timeout — generation takes ~11 min based on prior test).
4. Download MP3, send as Telegram voice bubble.

### Completion criterion

MP3 delivered to Telegram, or a clear error message if generation fails.

---

## File Layout

```
news-pipeline/
├── DESIGN.md              ← this file
├── sources.yaml           ← source definitions
├── interests.yaml.md      ← Mitran's interest profile (read by agent at runtime)
├── x_accounts.txt         ← 118 X accounts to scrape (one per line)
├── x_user_ids.json        ← cached user IDs (username → X user ID)
├── scripts/
│   └── fetch.py           ← Phase 1 fetch script (cron, no_agent)
├── prompts/
│   ├── phase2-verify.md   ← Phase 2: verify & clean (lightweight model)
│   ├── phase3-5-process.md ← Phase 3-5: process (frontier)
│   ├── phase5.5-freeroam.md ← Phase 5.5: free-roam (frontier)
│   ├── phase6-deliver.md  ← Phase 6: Telegram delivery (frontier)
│   └── phase7-podcast.md  ← Phase 7: NotebookLM podcast (on-demand)
├── data/
│   └── YYYY-MM-DD/        ← deleted after 30 days by fetch script
│       ├── fetch.log
│       ├── manifest.json
│       ├── raw_items.json
│       ├── cleaned_items.json    ← Phase 2 output
│       ├── health_report.json    ← Phase 2 output
│       ├── briefing.md           ← Phase 3-5 → Phase 5.5 → final
│       └── podcast-source.md     ← Phase 5.5 output
├── data/
│   └── delivered_history.json    ← rolling 7-day delivered items (cross-session dedup)
└── notebooks/
    └── registry.json      ← { "YYYY-MM-DD": "notebook-id", ... } — for cleanup
```

---

## Pipeline Architecture (v2 — Token-Efficient)

**Principle:** deterministic script does all mechanical work (0 tokens). lightweight model does cheap judgment (verify, dedup, SEO). Frontier model (frontier model) does real thinking — with freedom to deep-dive any item it finds interesting. A free-roam frontier agent runs before delivery.

### Phase 1 — Collect (Script, 0 tokens, ~4:00 AM)

Pure script (`no_agent=True`). Fetches all sources, parses, applies mechanical filters (T-24h time, engagement thresholds), extracts metadata + top comments + post body (first 500 chars). Stores clean JSON. No dedup, no SEO filter, no sentiment — those go to Phase 2.

**Script does:**
- Fetch each source (curl for RSS/API, Playwright for Reddit/X/GitHub trending).
- Parse (feedparser for RSS/Atom, json for APIs, DOM extraction for browser).
- Time filter: only items published within T-24h to T-0h.
- Engagement filter: HN points >10, Reddit score >10 (small subs) / >50 (large subs).
- Extract for discussion posts: post title + body (first 500 chars), top 10 comments by score (first 200 chars each), total comment count.
- Store as JSON per source.
- Write `fetch.log` + `manifest.json`.

**Script does NOT do:** dedup, SEO farm detection, sentiment, keyword filtering, chapter assignment. Those need judgment → model.

### Phase 2 — Verify & Clean (lightweight model, ~5K tokens, ~4:05 AM)

Cheap model. Reads `manifest.json` + raw items.

**Tasks:**
1. Verify fetch health — did all sources succeed? Any errors?
2. If errors → trigger script-based retries (not manual LLM work).
3. SEO farm detection — flag/drop items from known spam/SEO domains.
4. Dedup — URL normalization + title similarity. Keep first occurrence, note duplicates.
5. Flag items that look interesting for the frontier model's attention.

**Output:** cleaned item list as JSON, fetch health report.

### Phase 3-5 — Process (frontier model, ~60-80K tokens, ~4:10 AM)

Single LLM pass. Input: cleaned items from Phase 2. The model does hype assessment, chapter assignment, STE100 summary, and discussion TLDR in one call.

**The model has freedom here.** If it finds an item worth deep-diving:
- Fetch the linked article (web tools).
- Research the topic for latest context.
- Look up related news.
- Add background info that isn't in the headline.
The model decides what's worth the extra tokens, not the script.

**Output:** `briefing.md` with full annotations + deep-dives where warranted.

### Phase 5.5 — Free-Roam (frontier model, ~30-50K tokens, ~5:00 AM)

Free-roam agent before final delivery. Input: `briefing.md` from Phase 3-5.

**What it does: whatever it judges valuable.**
- Spot gaps in coverage.
- Cross-reference items (does story X from HN connect to story Y from Reddit?).
- Add context the first pass missed.
- Verify claims, check if something is actually hype vs substance.
- Reorder chapters if the ranking feels off.
- Flag items that should be in "Cool Shit" vs "AI".
- Research anything that needs more context.

**Output:** finalized `briefing.md` ready for delivery + `podcast-source.md`.

### Phase 6 — Deliver (frontier model, ~20K tokens, ~6:00 AM)

Reads finalized `briefing.md`. Formats DeArrow-style Telegram headlines with the friend voice. Sends Telegram message. Asks for `/podcast` approval. After delivery, appends delivered items to `data/delivered_history.json`.

### Cross-Session Dedup

Stories that stay viral across multiple days (e.g., Anthropic watermark — appeared Aug 12, 13, AND 14) used to repeat as fresh news every day. The pipeline now has a 7-day memory of what was delivered.

**File:** `data/delivered_history.json` — rolling 7-day record of delivered items (headline, URL, chapter, classification, date). ~40-60 items/day × 7 days = ~280-420 items.

**Data flow:**

| Phase | Role |
|---|---|
| Phase 1 (script) | Prunes history to 7 days. 0 tokens. |
| Phase 5.5 (free-roam) | Reads history + briefing. Semantic match: new / update / duplicate. |
| Phase 6 (deliver) | Appends today's delivered items to history. |

**Classifications:** `update` is a 4th classification, mutually exclusive with substance / hype / hype-worthy. An item is either new (gets one of the three) or an update. Not both.

**Matching:** the LLM does semantic matching — it reads past headlines and today's briefing and decides. No URL string matching. Same story from different sources (TechCrunch vs Reddit thread) gets caught because the model understands they're about the same event.

**Only delivered items count.** Items that made it to briefing.md but were trimmed by Phase 6 for length are not in history.

**↻ marker:** updates get ↻ in the Telegram message, parallel to 🔥 / 📊 / 💤.

### Phase 7 — Podcast (on-demand, ~15K tokens)

On `/podcast` reply: read `podcast-source.md`, create NotebookLM notebook, generate audio, download MP3, send as Telegram voice bubble. NotebookLM generation itself uses zero LLM tokens (Google API call).

### Estimated Daily Token Budget

| Component | Model | Est. Tokens |
|---|---|---|
| Phase 1 (fetch) | — | 0 |
| Phase 2 (verify + clean) | lightweight model | ~5K |
| Phase 3-5 (process + deep-dives) | frontier model | ~60-80K |
| Phase 5.5 (free-roam + cross-session dedup) | frontier model | ~32-52K |
| Phase 6 (deliver + history write) | frontier model | ~21K |
| **Daily total** | | **~118-164K** |
| Phase 7 (podcast, on-demand) | frontier model | ~15K |

### Toolsets per Phase

| Phase | Toolsets | Rationale |
|---|---|---|
| 1 (script) | none | Pure script |
| 2 (lightweight model) | `terminal` | Read files, run retry scripts |
| 3-5 (frontier) | `terminal`, `web` | Read items, fetch articles, research context |
| 5.5 (free-roam) | `terminal`, `web` | Full freedom to research, verify, cross-reference |
| 6 (deliver) | `terminal` | Read briefing, format, send |
| 7 (podcast) | `terminal` | Write source file, call NotebookLM API |

### No browser snapshots in the agent

- All browser work (Reddit, GitHub trending via Camofox REST API; X timelines via twscrape) done via scripts that extract structured JSON. The agent never sees raw DOM. This was the #1 token sink in past sessions.

---

## Resolved Decisions

1. **Sources** — fully defined in `sources.yaml` (54 RSS, 3 Google News, HN API, 29 Reddit subs, 118 X accounts, GitHub trending). Script is source-agnostic via `sources.yaml`.
2. **One agent for Phase 2–5** — single agent prompt, four explicit steps with completion criteria. Not split.
3. **NotebookLM notebook cleanup** — delete yesterday's notebook at the start of each podcast generation. Track notebook IDs in `notebooks/registry.json`.
4. **Data retention** — 30 days. Fetch script deletes `data/` dirs older than 30 days at the start of each run.
5. **Interest profile** — lives in `interests.yaml`, not hardcoded in prompts. Agent reads it at runtime.

## RSS Filtering Strategy

### The problem

54 RSS feeds + 3 Google News queries + HN API + Reddit + X = ~1000-2000 raw items/day. Many feeds publish 10-50 items/day. We can't send all of them to the LLM — that wastes tokens on old, irrelevant, or unpopular posts.

### The solution: pre-filter in the fetch script (no LLM needed)

The fetch script applies mechanical filters before storing items. Only items that pass these filters are stored in `data/YYYY-MM-DD/` and seen by the agent.

**Time filter (hardest cut):**
- Only items published within T-24h to T-0h (the 24 hours before fetch time).
- Parsed from `<pubDate>` (RSS) or `created_at_i` (HN API) or `published` (Atom).
- Items without a date are kept (can't filter what we can't date) but flagged.

**Engagement filter (for community sources only):**
- HN Algolia: `numericFilters=points>10` — drop items with <10 points.
- Reddit: filter by score after fetch (e.g., >10 for small subs, >50 for large subs). The fetch script reads the score from the DOM and drops low-score posts.
- Lobsters: filter by score if available in RSS, otherwise keep all (low volume).

**Deduplication (in Phase 2, not fetch script):**
- The fetch script does NOT dedup. Dedup is Phase 2's job (lightweight model).
- Phase 2 normalizes URLs (strip utm_*, ref, source, trailing slashes, fragments) and compares titles for similarity.
- Keeps first occurrence, notes duplicates.

**No keyword filtering at fetch time.**
The fetch script does not filter by topic — that's the agent's job. The script only cuts noise (old, low-engagement, duplicates). Everything else goes through.

### What the agent sees

After filtering, the agent should see ~200-400 clean items per day — still a lot, but manageable for an LLM with aggressive scoring. The agent's job is to rank, chapter, and summarize — not to filter noise (the script already did that).

### Anti-overengineering principle

The fetch script should be simple:
1. Fetch each source (curl or browser).
2. Parse (feedparser for RSS/Atom, json for APIs, DOM extraction for browser).
3. Apply time + engagement + dedup filters.
4. Store as JSON.
5. Write logs.

No complex NLP, no semantic similarity in the script. That's the agent's job. The script is mechanical and deterministic.

### Cookie expiry (NotebookLM)

Google cookies from `~/.claw-browser/profiles/mitrans-claw/Default/Cookies` expire. When they do, podcast generation fails with `AuthError`. Mitigation: the Phase 7 agent catches `AuthError`, reports it to Mitran ("NotebookLM auth expired — need a browser login refresh"), and does not retry silently. Cookie refresh requires a Playwright login flow on the persistent profile.

### Fetch script total failure

If the 4 AM fetch script fails entirely (network down, box restarted), the 4:05 agent reads an empty or missing `manifest.json`. The agent should: report "no data fetched today" to `briefing.md`, and the 6 AM delivery sends a short message: "📰 No data today — fetch failed. Will retry tomorrow." No empty briefing.

### Cron timezone

Hermes cron schedules use the system timezone. Verify the box is set to IST (+05:30) or adjust schedules accordingly. `0 4 * * *` must mean 4 AM IST, not UTC.

---

## Dependencies

| Dependency | Status | Notes |
|---|---|---|
| `feedparser` | ✅ Installed | RSS/Atom parsing |
| `twscrape` v0.20.0 | ✅ Installed | X timeline scraping, cookie auth, account "solovaris" |
| `notebooklm-py` v0.8.0 | ✅ Installed | Auth via browser cookies |
| Google cookies | ✅ Available | `~/.claw-browser/profiles/mitrans-claw/x_cookies.json` |
| X cookies | ✅ Available | Same path, `auth_token` + `ct0` |
| HN Algolia API | ✅ Live | Tested, returns JSON |
| Google News RSS | ✅ Live | Tested, 3 queries working |
| Tech blog RSS | ✅ Live | 54 feeds verified |
| Reddit via Camofox | ✅ Working | 29 subs, IIFE JS extraction |
| GitHub trending via Camofox | ✅ Working | 12 repos/day |
| X timelines via twscrape | ✅ Working | 118 accounts, ~35 min with rate limits |
| Camofox (browser) | ✅ Running | REST API on port 9377 |
| Telegram delivery | ✅ Proven | 2 existing cron jobs deliver to this chat |
