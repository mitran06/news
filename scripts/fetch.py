#!/usr/bin/env python3
"""Phase 1 fetch script — News Pipeline. No LLM. Mechanical only."""
import json, os, re, subprocess, time, shutil, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml, feedparser

SCRIPT_DIR = Path(__file__).resolve().parent.parent
SOURCES_FILE = SCRIPT_DIR / "sources.yaml"
DATA_DIR = SCRIPT_DIR / "data"
CAMOFOX = "http://localhost:9377"
CAMOFOX_USER = "mitrans-claw"
CAMOFOX_SESSION = "news-fetch"
GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
X_TRENDING_URL = "https://x.com/explore/tabs/trending"


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def camofox(method, path, body=None):
    """Camofox REST API call. Auto-injects userId/sessionKey."""
    if body is None:
        body = {}
    body.setdefault("userId", CAMOFOX_USER)
    body.setdefault("sessionKey", CAMOFOX_SESSION)
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "30", "-X", method,
             f"{CAMOFOX}{path}", "-H", "Content-Type: application/json",
             "-d", json.dumps(body)],
            capture_output=True, text=True, timeout=35)
        if r.returncode == 0 and r.stdout:
            return json.loads(r.stdout), None
        return None, r.stderr or "empty"
    except Exception as e:
        return None, str(e)


def fetch_url(url, timeout=15):
    """Fetch via curl. Returns (content, status, error)."""
    try:
        r = subprocess.run(
            ["curl", "-sL", "--connect-timeout", str(timeout),
             "--max-time", str(timeout + 5),
             "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
             url],
            capture_output=True, text=True, timeout=timeout + 10)
        if r.returncode == 0 and r.stdout:
            return r.stdout, 200, None
        return None, 0, r.stderr or "empty"
    except Exception as e:
        return None, 0, str(e)


def parse_date(s):
    if not s:
        return None
    try:
        return feedparser._parse_date(s)
    except Exception:
        pass
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def within_24h(dt):
    if dt is None:
        return None
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    age = now - dt
    return timedelta(hours=0) <= age <= timedelta(hours=24)


def clean_html(s):
    return re.sub(r"<[^>]+>", "", s).strip()[:500] if s else ""


# ── RSS feeds ──────────────────────────────────────────────

def fetch_rss(source):
    name, url = source["name"], source["url"]
    content, status, err = fetch_url(url)
    if err or not content:
        log(f"FETCH {name} → FAILED: {err}")
        return [], name, status, err
    feed = feedparser.parse(content)
    items = []
    # Cap items per feed to prevent volume explosion (arXiv publishes 200+ per feed per day)
    max_items = source.get("max_items", 50)
    for e in feed.entries[:max_items]:
        dt = parse_date(e.get("published", e.get("updated", "")))
        if within_24h(dt) is False:
            continue
        items.append({
            "title": e.get("title", "").strip(),
            "url": e.get("link", "").strip(),
            "source": name, "source_type": "rss",
            "published": dt.isoformat() if dt else None,
            "date_unknown": dt is None,
            "summary": clean_html(e.get("summary", "")),
        })
    log(f"FETCH {name} → {status} OK, {len(items)} items (T-24h, cap={max_items})")
    return items, name, status, None


# ── HN Algolia API ─────────────────────────────────────────

def fetch_hn(source):
    name = source["name"]
    ts = int((datetime.now() - timedelta(hours=24)).timestamp())
    base = source["url"]
    url = base + f",created_at_i%3E{ts}" if "numericFilters" in base else base + f"&numericFilters=created_at_i%3E{ts}"
    content, status, err = fetch_url(url)
    if err or not content:
        log(f"FETCH {name} → FAILED: {err}")
        return [], name, status, err
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        log(f"FETCH {name} → JSON error: {e}")
        return [], name, status, str(e)
    items = []
    for h in data.get("hits", []):
        ca = h.get("created_at_i", 0)
        if ca and ca < ts:
            continue
        dt = datetime.fromtimestamp(ca, tz=timezone.utc) if ca else None
        items.append({
            "title": h.get("title", ""),
            "url": h.get("url", "") or f"https://news.ycombinator.com/item?id={h.get('objectID', '')}",
            "source": source.get("name", "hn-algolia-top"), "source_type": "api",
            "published": dt.isoformat() if dt else None,
            "date_unknown": dt is None,
            "score": h.get("points", 0),
            "comments": h.get("num_comments", 0),
            "hn_id": h.get("objectID", ""),
            "author": h.get("author", ""),
        })
    log(f"FETCH {name} → {status} OK, {len(items)} items (T-24h, points>10)")
    return items, name, status, None


# ── Google News RSS ────────────────────────────────────────

def fetch_gnews(source):
    name = source["name"]
    q = urllib.parse.quote(source["query"])
    gl = source.get("gl", "US")
    hl = source.get("hl", "en-US")
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
    content, status, err = fetch_url(url)
    if err or not content:
        log(f"FETCH {name} → FAILED: {err}")
        return [], name, status, err
    feed = feedparser.parse(content)
    items = []
    for e in feed.entries:
        dt = parse_date(e.get("published", ""))
        if within_24h(dt) is False:
            continue
        items.append({
            "title": e.get("title", "").strip(),
            "url": e.get("link", "").strip(),
            "source": name, "source_type": "google-news",
            "published": dt.isoformat() if dt else None,
            "date_unknown": dt is None,
            "summary": clean_html(e.get("summary", "")),
        })
    log(f"FETCH {name} → {status} OK, {len(items)} items (T-24h)")
    return items, name, status, None


# ── Reddit via Camofox (old.reddit.com — static HTML, no rate limiting) ─────

REDDIT_JS = """(function() {
    var results = [];
    var seen = {};
    var posts = document.querySelectorAll('.thing.link');
    posts.forEach(function(post) {
        var titleEl = post.querySelector('a.title');
        if (!titleEl) return;
        var title = titleEl.textContent.trim();
        if (!title || seen[title]) return;
        seen[title] = true;
        var link = titleEl.href;
        var scoreEl = post.querySelector('.score.unvoted');
        var scoreText = scoreEl ? scoreEl.textContent : '0';
        var commentsEl = post.querySelector('a.comments');
        var commentsText = commentsEl ? commentsEl.textContent : '0';
        var permalink = commentsEl ? commentsEl.href : link;
        results.push({title: title, link: link, scoreText: scoreText, commentsText: commentsText, permalink: permalink});
    });
    return results;
})()"""

REDDIT_COMMENTS_JS = """(function() {
    var postBody = document.querySelector('.usertext-body .md');
    var bodyText = postBody ? postBody.innerText.substring(0, 500) : '';
    var comments = [];
    var commentEls = document.querySelectorAll('.comment');
    for (var i = 0; i < Math.min(commentEls.length, 10); i++) {
        var c = commentEls[i];
        var scoreEl = c.querySelector('.score.unvoted');
        var score = scoreEl ? scoreEl.textContent : '?';
        var mdEl = c.querySelector('.md');
        var text = mdEl ? mdEl.innerText.substring(0, 200) : '';
        if (text) comments.push('[' + score + '] ' + text);
    }
    return {body: bodyText, comments: comments};
})()"""


def parse_reddit_score(text):
    """Parse old Reddit score text like '17.0k' → 17000."""
    text = text.strip().lower().replace(' points', '').replace(' point', '')
    if 'k' in text:
        try:
            return int(float(text.replace('k', '')) * 1000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0


def parse_reddit_comments(text):
    """Parse old Reddit comment count like '814 comments' → 814."""
    text = text.strip().lower().replace(' comments', '').replace(' comment', '')
    if 'k' in text:
        try:
            return int(float(text.replace('k', '')) * 1000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0


def fetch_reddit(subs, thresholds):
    all_items = []
    errors = []
    tab, err = camofox("POST", "/tabs", {"url": "https://www.reddit.com"})
    if err or not tab or "tabId" not in tab:
        log(f"FETCH reddit → FAILED: {err}")
        return [], "reddit", 0, str(err)
    tab_id = tab["tabId"]
    log(f"FETCH reddit → Camofox tab {tab_id} (old.reddit.com)")

    for sub in subs:
        name = sub["name"]
        tier = sub.get("tier", 2)
        min_score = thresholds.get("reddit_tier1_min_score" if tier == 1 else "reddit_tier2_min_score", 10)
        try:
            camofox("POST", f"/tabs/{tab_id}/navigate", {"url": f"https://old.reddit.com/r/{name}/top/?t=day"})
            time.sleep(2)
            ev, ev_err = camofox("POST", f"/tabs/{tab_id}/evaluate", {"expression": REDDIT_JS})
            if ev_err or not ev:
                errors.append(f"r/{name}: {ev_err}")
                log(f"FETCH r/{name} → FAILED: {ev_err}")
                continue
            posts = ev.get("result", [])
            if isinstance(posts, str):
                try:
                    posts = json.loads(posts)
                except Exception:
                    posts = []
            for p in posts:
                score = parse_reddit_score(p.get("scoreText", "0"))
                comments = parse_reddit_comments(p.get("commentsText", "0"))
                if score < min_score:
                    continue
                all_items.append({
                    "title": p.get("title", ""), "url": p.get("permalink", p.get("link", "")),
                    "source": f"r/{name}", "source_type": "reddit",
                    "published": None, "date_unknown": True,
                    "score": score, "comments": comments,
                    "subreddit": name, "tier": tier,
                })
            count = len([p for p in posts if parse_reddit_score(p.get("scoreText", "0")) >= min_score])
            log(f"FETCH r/{name} → OK, {count} posts (score>={min_score})")
        except Exception as e:
            errors.append(f"r/{name}: {str(e)[:80]}")
            log(f"FETCH r/{name} → FAILED: {e}")

    # Comment extraction for high-engagement posts (old.reddit.com — no rate limiting, no tab rotation needed)
    hi_eng = [i for i in all_items if i.get("comments", 0) >= 50]
    log(f"REDDIT: {len(hi_eng)} high-engagement posts for comment extraction")
    for idx, item in enumerate(hi_eng):
        try:
            url = item["url"]
            if not url.startswith("http"):
                url = "https://old.reddit.com" + url
            elif "www.reddit.com" in url:
                url = url.replace("www.reddit.com", "old.reddit.com")
            camofox("POST", f"/tabs/{tab_id}/navigate", {"url": url})
            time.sleep(1.5)
            dv, de = camofox("POST", f"/tabs/{tab_id}/evaluate", {"expression": REDDIT_COMMENTS_JS})
            if not de and dv:
                d = dv.get("result", {})
                if isinstance(d, str):
                    try:
                        d = json.loads(d)
                    except Exception:
                        d = {}
                comments = d.get("comments", [])
                if comments:
                    item["discussion_body"] = d.get("body", "")
                    item["top_comments"] = comments
                    item["has_discussion_data"] = True
                else:
                    item["has_discussion_data"] = False
            else:
                item["has_discussion_data"] = False
        except Exception:
            item["has_discussion_data"] = False

        time.sleep(0.5)  # Light pacing

    camofox("DELETE", f"/tabs/{tab_id}")
    log(f"FETCH reddit → {len(all_items)} total items from {len(subs)} subs")
    return all_items, "reddit", 200, "; ".join(errors) if errors else None


# ── GitHub Trending via Camofox ────────────────────────────

GITHUB_JS = """(function() {
    var results = [];
    var articles = document.querySelectorAll('article.Box-row');
    articles.forEach(function(article) {
        var nameEl = article.querySelector('h2 a');
        var name = nameEl ? nameEl.getAttribute('href').replace('/', '') : '';
        var descEl = article.querySelector('p');
        var desc = descEl ? descEl.textContent.trim() : '';
        var langEl = article.querySelector('[itemprop="programmingLanguage"]');
        var lang = langEl ? langEl.textContent.trim() : '';
        if (name) results.push({name: name, desc: desc, lang: lang, url: 'https://github.com/' + name});
    });
    return results;
})()"""


def camofox_cleanup(userId=None):
    """Close all open tabs for a user to prevent tab exhaustion."""
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "10",
             f"{CAMOFOX}/tabs?userId={userId or CAMOFOX_USER}"],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout:
            data = json.loads(r.stdout)
            tabs = data.get("tabs", [])
            for t in tabs:
                tid = t.get("tabId", "")
                if tid:
                    subprocess.run(
                        ["curl", "-sL", "--max-time", "5", "-X", "DELETE",
                         f"{CAMOFOX}/tabs/{tid}", "-H", "Content-Type: application/json",
                         "-d", json.dumps({"userId": userId or CAMOFOX_USER})],
                        capture_output=True, timeout=8)
            if tabs:
                log(f"CLEANUP closed {len(tabs)} stale Camofox tabs")
        else:
            log(f"CLEANUP failed: curl returned {r.returncode}, stderr={r.stderr[:100] if r.stderr else 'none'}")
    except Exception as e:
        log(f"CLEANUP failed: {e}")


def camofox_open_tab(url, session_key, retries=2):
    """Open a Camofox tab with retry. Cleans stale tabs first if needed."""
    for attempt in range(retries + 1):
        tab, err = camofox("POST", "/tabs", {"url": url, "sessionKey": session_key})
        if not err and tab and "tabId" in tab:
            return tab["tabId"], None
        if attempt < retries:
            log(f"  Tab creation failed (attempt {attempt+1}): {err}. Cleaning up and retrying...")
            camofox_cleanup()
            time.sleep(2)
    return None, err or "tab creation failed after retries"


def fetch_github():
    items = []
    camofox_cleanup()
    tab_id, err = camofox_open_tab("https://github.com/trending?since=daily", "github-trending")
    if err:
        log(f"FETCH github-trending → FAILED: {err}")
        return [], "github-trending", 0, str(err)
    time.sleep(4)
    ev, ev_err = camofox("POST", f"/tabs/{tab_id}/evaluate", {"expression": GITHUB_JS})
    if not ev_err and ev:
        repos = ev.get("result", [])
        if isinstance(repos, str):
            try:
                repos = json.loads(repos)
            except Exception:
                repos = []
        for r in repos:
            items.append({
                "title": f"{r.get('name', '')} — {r.get('desc', '')[:100]}",
                "url": r.get("url", ""), "source": "github-trending",
                "source_type": "browser", "published": None, "date_unknown": True,
                "language": r.get("lang", ""),
            })
        log(f"FETCH github-trending → OK, {len(items)} repos")
    else:
        log(f"FETCH github-trending → FAILED: {ev_err}")
    camofox("DELETE", f"/tabs/{tab_id}")
    return items, "github-trending", 200, ev_err


# ── X Trending via Camofox ─────────────────────────────────

X_JS = """(function() {
    var results = [];
    var els = document.querySelectorAll('[data-testid="trend"]');
    els.forEach(function(el) {
        var text = el.innerText.trim();
        if (text) results.push(text);
    });
    return results;
})()"""

def fetch_x():
    """Fetch tweets from followed accounts via twscrape. Also grabs X trending via twscrape."""
    items = []
    x_last_error = None

    # ── Twscrape: timelines from followed accounts ──
    try:
        import asyncio
        from twscrape import API, gather

        async def scrape_timelines():
            api = API()
            
            # CRITICAL: Reset stale rate limit locks from previous runs
            # twscrape persists locks in accounts.db — if a previous run was killed
            # mid-batch, locks stay stale and the next run produces 0 items
            await api.pool.reset_locks()
            log("FETCH x-timelines → rate limit locks reset")

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            # Load followed accounts list
            accounts_file = SCRIPT_DIR / "x_accounts.txt"
            if not accounts_file.exists():
                log("FETCH x-timelines → no x_accounts.txt found, skipping")
                return []

            usernames = [l.strip() for l in accounts_file.read_text().splitlines() if l.strip()]
            log(f"FETCH x-timelines → {len(usernames)} accounts to scrape")

            # Load cached user IDs
            id_cache_file = SCRIPT_DIR / "x_user_ids.json"
            id_cache = {}
            if id_cache_file.exists():
                id_cache = json.loads(id_cache_file.read_text())
                log(f"  {len(id_cache)} cached user IDs")

            # Resolve uncached usernames
            uncached = [u for u in usernames if u not in id_cache]
            if uncached:
                log(f"  Resolving {len(uncached)} uncached usernames...")
                for i, username in enumerate(uncached):
                    try:
                        user = await api.user_by_login(username)
                        id_cache[username] = int(user.id)
                    except Exception as e:
                        log(f"  ❌ {username}: {str(e)[:60]}")
                    if (i + 1) % 90 == 0 and i < len(uncached) - 1:
                        log("  Rate limit pause (90 resolved)...")
                        await asyncio.sleep(920)
                    await asyncio.sleep(0.3)
                id_cache_file.write_text(json.dumps(id_cache, indent=2))

            # ── Resume support + time budget ──
            # X tweets are saved incrementally to data/<TODAY>/x_partial.json
            # (username -> tweet items). If a previous run was killed mid-batch,
            # this run resumes from the partial file instead of starting over.
            # A time budget guarantees fetch.py ALWAYS exits cleanly (writes
            # manifest.json) instead of being killed by the cron timeout.
            tdir = DATA_DIR / datetime.now().strftime("%Y-%m-%d")
            tdir.mkdir(parents=True, exist_ok=True)
            partial_file = tdir / "x_partial.json"
            partial = {}
            if partial_file.exists():
                try:
                    partial = json.loads(partial_file.read_text())
                    log(f"  resuming: {len(partial)} accounts already in partial file")
                except Exception:
                    partial = {}

            X_TIME_BUDGET = 3300  # seconds; fetch.py must finish within the cron timeout
            x_deadline = time.monotonic() + X_TIME_BUDGET

            # Fetch timelines in batches (50 per 15 min rate limit)
            # With reset_locks, the first batch always works cleanly
            BATCH_SIZE = 45

            for batch_start in range(0, len(usernames), BATCH_SIZE):
                batch_num = batch_start // BATCH_SIZE + 1
                batch = usernames[batch_start:batch_start + BATCH_SIZE]
                if batch_num > 1:
                    if time.monotonic() > x_deadline - 960:
                        log(f"  ⏱ X time budget reached before batch {batch_num} — stopping cleanly ({len(partial)}/{len(usernames)} accounts done)")
                        break
                    log(f"  Rate limit wait before batch {batch_num}...")
                    await asyncio.sleep(920)

                for i, username in enumerate(batch):
                    if username in partial:
                        continue  # already fetched in an earlier (killed) run today
                    uid = id_cache.get(username)
                    if not uid:
                        continue
                    if time.monotonic() > x_deadline:
                        log(f"  ⏱ X time budget reached mid-batch {batch_num} — stopping cleanly ({len(partial)}/{len(usernames)} accounts done)")
                        break
                    try:
                        tweets = await gather(api.user_tweets(uid, limit=20))
                        recent = [t for t in tweets if t.date and t.date > cutoff]
                        partial[username] = [{
                            "title": f"@{username}: {t.rawContent[:120]}",
                            "url": t.url,
                            "source": f"x/@{username}",
                            "source_type": "x-timeline",
                            "published": t.date.isoformat() if t.date else None,
                            "date_unknown": t.date is None,
                            "score": t.likeCount or 0,
                            "retweets": t.retweetCount or 0,
                            "replies": t.replyCount or 0,
                            "views": t.viewCount or 0,
                            "username": username,
                            "tweet_id": t.id,
                        } for t in recent]
                        if recent:
                            log(f"  [{batch_start+i+1:3d}] ✅ {username:20s} | {len(recent):2d} T-24h")
                    except Exception as e:
                        log(f"  [{batch_start+i+1:3d}] ❌ {username:20s} | {str(e)[:60]}")
                    # Incremental save after every account — survives kills
                    partial_file.write_text(json.dumps(partial, ensure_ascii=False))
                else:
                    continue
                break  # inner budget break → stop outer loop too

            all_tweets = [t for tweets in partial.values() for t in tweets]
            log(f"  X timelines complete: {len(all_tweets)} tweets from {len(partial)} accounts")

            return all_tweets

        tw_items = asyncio.run(scrape_timelines())
        items.extend(tw_items)
        log(f"FETCH x-timelines → {len(tw_items)} tweets from followed accounts")
        x_last_error = None
    except ImportError:
        log("FETCH x-timelines → twscrape not installed, skipping")
        x_last_error = "twscrape not installed"
    except Exception as e:
        log(f"FETCH x-timelines → FAILED: {e}")
        x_last_error = f"{type(e).__name__}: {str(e)[:200]}"

    # ── Camofox: X trending (fallback — twscrape trends endpoint returns 0) ──
    try:
        camofox_cleanup()
        tab_id, err = camofox_open_tab(X_TRENDING_URL, "x-trending")
        if not err and tab_id:
            time.sleep(5)
            ev, ev_err = camofox("POST", f"/tabs/{tab_id}/evaluate", {"expression": X_JS})
            if not ev_err and ev:
                trends = ev.get("result", [])
                if isinstance(trends, str):
                    try:
                        trends = json.loads(trends)
                    except Exception:
                        trends = []
                for t in trends:
                    lines = t.split("\n")
                    topic = lines[-1] if lines else t
                    cat = lines[0] if len(lines) > 1 else ""
                    items.append({
                        "title": topic,
                        "url": f"https://x.com/search?q={urllib.parse.quote(topic)}",
                        "source": "x-trending", "source_type": "browser",
                        "published": None, "date_unknown": True,
                        "category": cat, "raw": t,
                    })
                log(f"FETCH x-trending → OK (Camofox), {len(trends)} trends")
            else:
                log(f"FETCH x-trending → FAILED: {ev_err}")
            camofox("DELETE", f"/tabs/{tab_id}")
        else:
            log(f"FETCH x-trending → FAILED: {err}")
    except Exception as e:
        log(f"FETCH x-trending → FAILED: {e}")

    # Return items, plus separate status info for timelines and trending
    timeline_items = [i for i in items if i.get("source_type") == "x-timeline"]
    trending_items = [i for i in items if i.get("source") == "x-trending"]
    return items, {"timelines": len(timeline_items), "trending": len(trending_items)}

# ── Main ───────────────────────────────────────────────────

def main():
    log("START fetch")
    with open(SOURCES_FILE) as f:
        cfg = yaml.safe_load(f)

    # Cleanup old data
    cutoff = datetime.now() - timedelta(days=cfg.get("retention_days", 30))
    if DATA_DIR.exists():
        for d in DATA_DIR.iterdir():
            if not d.is_dir():
                continue
            try:
                if datetime.strptime(d.name, "%Y-%m-%d") < cutoff:
                    shutil.rmtree(d)
                    log(f"CLEANUP deleted {d.name}")
            except ValueError:
                continue

    # Prune delivered_history.json to 7 days
    history_path = DATA_DIR / "delivered_history.json"
    if history_path.exists():
        try:
            with open(history_path) as f:
                history = json.load(f)
            cutoff_str = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            pruned = [h for h in history if h.get("date", "") >= cutoff_str]
            if len(pruned) < len(history):
                with open(history_path, "w") as f:
                    json.dump(pruned, f, indent=2)
                log(f"HISTORY pruned {len(history)} → {len(pruned)} entries (7-day window)")
        except (json.JSONDecodeError, IOError) as e:
            log(f"HISTORY prune skipped: {e}")

    today = datetime.now().strftime("%Y-%m-%d")
    tdir = DATA_DIR / today
    tdir.mkdir(parents=True, exist_ok=True)

    all_items = []
    flog = []
    ok = 0
    failed = 0
    failed_names = []

    # RSS
    for s in cfg.get("rss_feeds", []):
        items, name, status, err = fetch_rss(s)
        all_items.extend(items)
        ok += 1 if not err else 0
        failed += 1 if err else 0
        if err:
            failed_names.append(name)
        flog.append({"source": name, "type": "rss", "status": status, "items": len(items), "error": err})

    # HN API
    for s in cfg.get("api_sources", []):
        items, name, status, err = fetch_hn(s)
        all_items.extend(items)
        ok += 1 if not err else 0
        failed += 1 if err else 0
        if err:
            failed_names.append(name)
        flog.append({"source": name, "type": "api", "status": status, "items": len(items), "error": err})

    # Google News
    for s in cfg.get("google_news_queries", []):
        items, name, status, err = fetch_gnews(s)
        all_items.extend(items)
        ok += 1 if not err else 0
        failed += 1 if err else 0
        if err:
            failed_names.append(name)
        flog.append({"source": name, "type": "google-news", "status": status, "items": len(items), "error": err})

    # Reddit
    subs = cfg.get("reddit_subreddits", [])
    thresholds = cfg.get("thresholds", {})
    if subs:
        items, name, status, err = fetch_reddit(subs, thresholds)
        all_items.extend(items)
        ok += 1 if not (err and not items) else 0
        failed += 1 if (err and not items) else 0
        if err and not items:
            failed_names.append("reddit")
        flog.append({"source": "reddit", "type": "browser", "status": status, "items": len(items), "error": err})

    # GitHub
    items, name, status, err = fetch_github()
    all_items.extend(items)
    ok += 1 if not (err and not items) else 0
    failed += 1 if (err and not items) else 0
    if err and not items:
        failed_names.append("github-trending")
    flog.append({"source": "github-trending", "type": "browser", "status": status, "items": len(items), "error": err})

    # Save intermediate data before X fetch (in case X times out)
    with open(tdir / "raw_items.json", "w") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    log(f"  (intermediate save before X: {len(all_items)} items)")

    # X (timelines + trending)
    items = []
    try:
        items, x_info = fetch_x()
        all_items.extend(items)
    except Exception as e:
        log(f"FETCH x → FAILED: {e}")
        x_info = {"timelines": 0, "trending": 0}
        x_last_error = f"{type(e).__name__}: {str(e)[:200]}"
    ok += 1 if items else 0
    if not items:
        failed_names.append("x")
    flog.append({"source": "x-timelines", "type": "twscrape", "status": 200 if x_info["timelines"] else 0, "items": x_info["timelines"], "error": (x_last_error or "no tweets (per-account fetch errors or all accounts inactive)") if not x_info["timelines"] else None})
    flog.append({"source": "x-trending", "type": "browser", "status": 200 if x_info["trending"] else 0, "items": x_info["trending"], "error": "no trends (Camofox session or timing issue)" if not x_info["trending"] else None})

    # Write outputs
    with open(tdir / "raw_items.json", "w") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    log(f"  (intermediate save: {len(all_items)} items)")

    with open(tdir / "fetch.log", "w") as f:
        for e in flog:
            line = f"{e['source']} | {e['type']} | status={e['status']} | items={e['items']}"
            if e["error"]:
                line += f" | ERROR: {e['error']}"
            f.write(line + "\n")

    manifest = {
        "date": today, "fetched_at": datetime.now().isoformat(),
        "sources_fetched": ok + failed, "sources_ok": ok, "sources_failed": failed,
        "total_items": len(all_items), "failed_sources": failed_names,
    }
    with open(tdir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    log(f"SUMMARY: {ok + failed} fetched, {ok} ok, {failed} failed, {len(all_items)} total items")
    if failed_names:
        log(f"FAILED: {failed_names}")
    print(f"\nManifest: {tdir / 'manifest.json'}")
    print(f"Items: {tdir / 'raw_items.json'}")


if __name__ == "__main__":
    main()
