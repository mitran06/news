#!/usr/bin/env python3
"""
Observability logger — runs deterministically after each phase.
Zero token overhead. Diffs input/output files to infer what the agent did.

Usage:
    python3 scripts/phase_logger.py <phase> <today>

Phases:
    phase3-5   — diff cleaned_items.json vs briefing.md → dropped items
    phase5.5   — diff briefing.md before/after → changes
    phase6     — snapshot delivered_history.json delta + briefing.md → delivered items
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def load_json(path):
    if not Path(path).exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_text(path):
    if not Path(path).exists():
        return None
    with open(path) as f:
        return f.read()


def extract_urls_from_briefing(text):
    """Extract all URLs from briefing.md"""
    if not text:
        return set()
    # Match markdown links and bare URLs
    urls = set(re.findall(r'https?://[^\s\)]+', text))
    return urls


def extract_urls_from_items(items):
    """Extract URLs from cleaned_items.json"""
    urls = set()
    for item in items:
        url = item.get("url", "")
        if url:
            # Normalize: strip trailing slash
            urls.add(url.rstrip("/"))
    return urls


def log_phase3_5(data_dir, log_dir):
    """Diff cleaned_items.json vs briefing.md → items not in briefing = dropped."""
    cleaned = load_json(f"{data_dir}/cleaned_items.json")
    briefing = load_text(f"{data_dir}/briefing.md")

    if cleaned is None:
        return {"error": "cleaned_items.json not found"}
    if briefing is None:
        return {"error": "briefing.md not found"}

    briefing_urls = extract_urls_from_briefing(briefing)

    dropped = []
    for item in cleaned:
        url = item.get("url", "").rstrip("/")
        title = item.get("title", "")
        source = item.get("source", "")
        score = item.get("score", 0)

        # Check if this item's URL appears in the briefing
        found = False
        for bu in briefing_urls:
            if url and url in bu:
                found = True
                break
            # Also try matching without protocol differences
            if url and bu and url.replace("https://", "").replace("http://", "") in bu.replace("https://", "").replace("http://", ""):
                found = True
                break

        if not found:
            dropped.append({
                "title": title,
                "url": item.get("url", ""),
                "source": source,
                "score": score,
            })

    return {
        "phase": "phase3-5",
        "timestamp": datetime.now().isoformat(),
        "items_in": len(cleaned),
        "items_in_briefing": len(cleaned) - len(dropped),
        "items_dropped": len(dropped),
        "dropped": dropped,
    }


def log_phase5_5(data_dir, log_dir):
    """Diff briefing.md before and after free-roam.
    We snapshot the pre-free-roam briefing in phase_logs/briefing_pre_freeroam.md
    before Phase 5.5 runs, then diff after.
    """
    pre_path = f"{log_dir}/briefing_pre_freeroam.md"
    post_briefing = load_text(f"{data_dir}/briefing.md")
    pre_briefing = load_text(pre_path)

    if pre_briefing is None:
        return {"error": "briefing_pre_freeroam.md not found — was the pre-snapshot taken?"}
    if post_briefing is None:
        return {"error": "briefing.md not found after Phase 5.5"}

    pre_urls = extract_urls_from_briefing(pre_briefing)
    post_urls = extract_urls_from_briefing(post_briefing)

    added = post_urls - pre_urls
    removed = pre_urls - post_urls

    # Extract headlines (### lines) for more readable diff
    pre_headlines = set(re.findall(r'^###\s+(.+)$', pre_briefing, re.MULTILINE))
    post_headlines = set(re.findall(r'^###\s+(.+)$', post_briefing, re.MULTILINE))

    added_headlines = post_headlines - pre_headlines
    removed_headlines = pre_headlines - post_headlines

    # Check for Dropped Duplicates section
    dropped_dups = []
    dup_section = re.search(r'## Dropped Duplicates\s*\n(.*?)(?=\n##|\Z)', post_briefing, re.DOTALL)
    if dup_section:
        for line in dup_section.group(1).strip().split("\n"):
            line = line.strip()
            if line:
                dropped_dups.append(line)

    return {
        "phase": "phase5.5",
        "timestamp": datetime.now().isoformat(),
        "headlines_before": len(pre_headlines),
        "headlines_after": len(post_headlines),
        "urls_added": list(added),
        "urls_removed": list(removed),
        "headlines_added": list(added_headlines),
        "headlines_removed": list(removed_headlines),
        "dropped_duplicates": dropped_dups,
    }


def log_phase6(data_dir, log_dir):
    """Snapshot what was delivered by checking delivered_history.json delta."""
    history = load_json(f"{data_dir}/delivered_history.json")
    briefing = load_text(f"{data_dir}/briefing.md")

    if history is None:
        return {"error": "delivered_history.json not found"}

    # Get today's entries
    today_str = Path(data_dir).name  # e.g. "2026-08-20"
    today_entries = [e for e in history if e.get("date") == today_str]

    return {
        "phase": "phase6",
        "timestamp": datetime.now().isoformat(),
        "items_delivered": len(today_entries),
        "delivered": today_entries,
        "briefing_headlines": re.findall(r'^###\s+(.+)$', briefing or "", re.MULTILINE),
        "briefing_url_count": len(extract_urls_from_briefing(briefing)),
    }


def snapshot_pre_freeroam(data_dir, log_dir):
    """Copy briefing.md to phase_logs/briefing_pre_freeroam.md before Phase 5.5 runs."""
    briefing = load_text(f"{data_dir}/briefing.md")
    if briefing:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        with open(f"{log_dir}/briefing_pre_freeroam.md", "w") as f:
            f.write(briefing)
        print(f"  Snapshotted pre-free-roam briefing ({len(briefing)} chars)")
    else:
        print("  WARNING: briefing.md not found for pre-free-roam snapshot")


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 scripts/phase_logger.py <phase> <today>")
        print("Phases: phase3-5, phase5.5-pre, phase5.5, phase6")
        sys.exit(1)

    phase = sys.argv[1]
    today = sys.argv[2]

    base = Path(__file__).parent.parent
    data_dir = str(base / "data" / today)
    log_dir = str(base / "data" / today / "phase_logs")

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    if phase == "phase5.5-pre":
        snapshot_pre_freeroam(data_dir, log_dir)
        return

    if phase == "phase3-5":
        result = log_phase3_5(data_dir, log_dir)
    elif phase == "phase5.5":
        result = log_phase5_5(data_dir, log_dir)
    elif phase == "phase6":
        result = log_phase6(data_dir, log_dir)
    else:
        print(f"Unknown phase: {phase}")
        sys.exit(1)

    log_file = f"{log_dir}/{phase}.json"
    with open(log_file, "w") as f:
        json.dump(result, f, indent=2)

    # Summary to stdout
    if "error" in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  Logged {log_file}")
        for k, v in result.items():
            if k in ("dropped", "delivered", "urls_added", "urls_removed",
                      "headlines_added", "headlines_removed", "dropped_duplicates",
                      "briefing_headlines"):
                print(f"    {k}: {len(v)} items")
            elif k != "timestamp" and k != "phase":
                print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
