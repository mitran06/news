# News Pipeline Sources — Confirmed

**Last updated:** August 10, 2026

## Reddit (Browser via Camofox, logged in as u/MitransClaw)

Fetch: `reddit.com/r/{sub}/top/?t=day` — top posts from T-24h.

### Subreddits (Tier 1 + Tier 2 only, nice-to-haves removed)

| # | Subreddit | Category | Why |
|---|---|---|---|
| 1 | r/LocalLLaMA | AI/ML | Open-source LLMs, model releases — ground zero |
| 2 | r/ClaudeAI | AI/Company | Claude/Anthropic, Claude Code (1.8M weekly visitors) |
| 3 | r/ChatGPT | AI/Company | OpenAI/GPT breaking news (11.5M subs) |
| 4 | r/singularity | AI/ML | AI news, viral stories (great for hype filter) |
| 5 | r/AI_Agents | AI/Agents | Agent frameworks (LangGraph, CrewAI, etc.) |
| 6 | r/ClaudeCode | AI/Company | Claude Code specifically (817K weekly visitors) |
| 7 | r/technology | General Tech | Broad tech news (15.3M subs) |
| 8 | r/startups | Startup | Startup ecosystem |
| 9 | r/cybersecurity | Security | Security news, breaches, CVEs |
| 10 | r/developersIndia | India | India dev community (427K weekly) |
| 11 | r/OpenAI | AI/Company | OpenAI company news |
| 12 | r/Anthropic | AI/Company | Anthropic company news |
| 13 | r/GeminiAI | AI/Company | Google Gemini |
| 14 | r/artificial | AI/ML | General AI news |
| 15 | r/LLMDevs | AI/Dev | LLM development |
| 16 | r/ChatGPTCoding | AI/Dev | AI-assisted coding |
| 17 | r/SideProject | Startup | Indie dev projects |
| 18 | r/YCombinator | Startup | YC startups |
| 19 | r/selfhosted | Dev/OSS | Self-hosting |
| 20 | r/devops | Dev/OSS | DevOps practices |
| 21 | r/nvidia | Hardware | GPU/AI hardware |
| 22 | r/netsec | Security | Technical security |
| 23 | r/privacy | Security | Privacy news |
| 24 | r/Entrepreneur | Startup | Business building |
| 25 | r/Futurology | General | Future tech, science |
| 26 | r/opensource | Dev/OSS | Open source news |
| 27 | r/sysadmin | Dev/OSS | Sysadmin/infra |
| 28 | r/experienceddevs | Dev | Senior dev perspectives |
| 29 | r/cscareerquestions | Dev | Industry trends, layoffs, hiring |

**Removed per Mitran's request:** r/MachineLearning, r/programming, r/webdev, r/javascript, r/linux, r/hardware, r/chipdesign, r/bangalore, r/IndiaTech, and all Tier 3.

## RSS Feeds (curl, all verified HTTP 200)

### Tier 1 — Must-Have

| Category | Source | RSS Feed URL |
|---|---|---|
| Bleeding edge | Hacker News | `https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=30&numericFilters=created_at_i>{ts}` (API) |
| Bleeding edge | Hacker News RSS | `https://hnrss.org/frontpage` |
| Bleeding edge | Lobsters | `https://lobste.rs/rss` |
| Bleeding edge | Techmeme | `https://www.techmeme.com/feed.xml` |
| General tech | Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` |
| General tech | The Verge | `https://www.theverge.com/rss/index.xml` |
| General tech | TechCrunch | `https://techcrunch.com/feed/` |
| General tech | The Register | `https://www.theregister.com/headlines.atom` |
| AI/ML | MIT Tech Review | `https://www.technologyreview.com/feed/` |
| AI/ML | OpenAI Blog | `https://openai.com/blog/rss.xml` |
| AI/ML | Google AI Blog | `https://blog.google/technology/ai/rss/` |
| AI/ML | Hugging Face | `https://huggingface.co/blog/feed.xml` |
| AI/ML | arXiv cs.AI | `https://arxiv.org/rss/cs.AI` |
| AI/ML | arXiv cs.LG | `https://arxiv.org/rss/cs.LG` |
| AI/ML | arXiv cs.CL | `https://arxiv.org/rss/cs.CL` |
| Developer | GitHub Blog | `https://github.blog/feed/` |
| Developer | InfoQ | `https://www.infoq.com/feed/` |
| Developer | LWN.net | `https://lwn.net/headlines/rss` |
| Developer | Dev.to | `https://dev.to/feed` |
| Startup | TechCrunch Startups | `https://techcrunch.com/category/startups/feed/` |
| Startup | Stratechery | `https://stratechery.com/feed/` |
| Science | Nature | `https://feeds.nature.com/nature/rss/current` |
| Science | Quanta Magazine | `https://www.quantamagazine.org/feed/` |
| Hardware | Tom's Hardware | `https://www.tomshardware.com/feeds/all` |
| Hardware | ServeTheHome | `https://www.servethehome.com/feed/` |
| Security | The Hacker News | `https://feeds.feedburner.com/TheHackersNews` |
| Security | BleepingComputer | `https://www.bleepingcomputer.com/feed/` |
| Security | Krebs on Security | `https://krebsonsecurity.com/feed/` |
| Security | Schneier on Security | `https://www.schneier.com/feed/atom/` |
| Newsletter | TLDR | `https://tldr.tech/rss` |
| Newsletter | Import AI | `https://importai.substack.com/feed` |

### Tier 2 — Strong Additions

| Category | Source | RSS Feed URL |
|---|---|---|
| General | Wired | `https://www.wired.com/feed/rss` |
| General | BBC Tech | `https://feeds.bbci.co.uk/news/technology/rss.xml` |
| General | IEEE Spectrum | `https://spectrum.ieee.org/feeds/feed.rss` |
| AI/ML | NVIDIA Blog | `https://blogs.nvidia.com/feed/` |
| AI/ML | Microsoft Research | `https://www.microsoft.com/en-us/research/feed/` |
| AI/ML | Google Research | `https://research.google/blog/rss/` |
| AI/ML | Latent Space | `https://www.latent.space/feed` |
| AI/ML | Last Week in AI | `https://www.lastweekinai.com/feed` |
| Dev | Cloudflare Blog | `https://blog.cloudflare.com/rss/` |
| Dev | Netflix TechBlog | `https://netflixtechblog.com/feed` |
| Dev | Meta Engineering | `https://engineering.fb.com/feed/` |
| Dev | Phoronix | `https://www.phoronix.com/rss.php` |
| Dev | Stack Overflow Blog | `https://stackoverflow.blog/feed/` |
| Startup | Sifted | `https://sifted.eu/feed/` |
| Startup | StrictlyVC | `https://www.strictlyvc.com/feed` |
| Science | ScienceDaily | `https://rss.sciencedaily.com/all.xml` |
| Science | Science Magazine | `https://www.science.org/rss/news_current.xml` |
| Hardware | SemiEngineering | `https://semiengineering.com/feed/` |
| Hardware | EE Times | `https://www.eetimes.com/feed/` |
| Hardware | TechPowerUp | `https://www.techpowerup.com/rss` |
| Security | Dark Reading | `https://www.darkreading.com/rss.xml` |
| Security | SecurityWeek | `https://www.securityweek.com/feed/` |
| Aggregator | Product Hunt | `https://www.producthunt.com/feed` |
| Aggregator | Slashdot | `https://rss.slashdot.org/Slashdot/slashdotMain` |

## X/Twitter (Browser via persistent Playwright profile)

### Following (130 existing + 17 new = 147 total)

**New accounts followed (Aug 10, 2026):**
@karpathy, @ylecun, @AndrewYNg, @fchollet, @swyx, @TechCrunch, @HackerNews, @Wired, @arstechnica, @TheInformation, @github, @Vercel, @Cloudflare, @AnthropicAI, @OpenAI, @GoogleAI, @nasscom

### X Trending

Fetch: `x.com/explore/tabs/trending` — filter for tech/AI-related trending topics only. Discard sports, entertainment, politics (unless tech-adjacent or globally significant).

## Google News RSS (curl)

| Query | URL |
|---|---|
| General tech | `https://news.google.com/rss/search?q=technology+OR+AI+OR+startup&hl=en-US&gl=US&ceid=US:en` |
| X/Twitter proxy | `https://news.google.com/rss/search?q=site:x.com+OR+site:twitter.com&hl=en-US&gl=US&ceid=US:en` |
| India tech | `https://news.google.com/rss/search?q=Bangalore+technology+OR+startup&hl=en-IN&gl=IN&ceid=IN:en` |

## Browser-Only Sources

| Source | URL | Method |
|---|---|---|
| Reddit subreddits | `reddit.com/r/{sub}/top/?t=day` | Camofox (logged in as u/MitransClaw) |
| X Trending | `x.com/explore/tabs/trending` | Persistent Playwright profile |
| GitHub Trending | `github.com/trending?since=daily` | Camofox or Playwright |

## Fetch Method Summary

| Method | Sources | Count |
|---|---|---|
| RSS/Atom (curl) | 54 feeds | ~500-1000 items/day |
| API (curl JSON) | HN Algolia | ~300-700 items/day |
| Browser (Camofox) | 29 Reddit subs | ~200-500 posts/day |
| Browser (Playwright) | X trending | ~10-30 topics/day |
| Browser (Camofox) | GitHub trending | ~25 repos/day |
| RSS (curl) | Google News (3 queries) | ~30-60 items/day |
| **Total estimated** | | **~1000-2000 raw items/day** |
