#!/usr/bin/env python3
"""
Observability logger — runs deterministically after each phase.
Zero token overhead. Diffs input/output files to infer what the agent did.

Usage:
    python3 scripts/phase_logger.py <phase> <today>

Phases:
    phase3-5     — diff cleaned_items.json vs briefing.md → dropped items
    phase5.5-pre — snapshot briefing.md before free-roam
    phase5.5     — diff briefing.md before/after → changes
    phase6       — snapshot delivered items from history
    reasoning    — extract per-phase reasoning from session DB (run once at end)
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


def log_reasoning(data_dir, log_dir, today):
    """Extract per-phase reasoning from the Hermes session DB.

    Finds the cron session for today, gets all messages in order,
    splits at phase_logger.py tool-call boundaries, writes per-phase
    reasoning files with both assistant text and model reasoning.
    """
    import sqlite3
    from datetime import datetime as dt

    db_path = os.path.expanduser("~/.hermes/state.db")
    if not os.path.exists(db_path):
        print("  ERROR: state.db not found")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Find today's cron session — title format: "news-pipeline · Aug 19 05:18"
    # Match by date in started_at timestamp (more reliable than title, which
    # may not be committed yet if the session is still active).
    try:
        dt_obj = dt.strptime(today, "%Y-%m-%d")
        day_start = dt_obj.timestamp()
        day_end = dt_obj.replace(hour=23, minute=59, second=59).timestamp()
    except ValueError:
        day_start = 0
        day_end = float('inf')

    cur.execute("""
        SELECT id FROM sessions
        WHERE source = 'cron' AND started_at >= ? AND started_at <= ?
        ORDER BY started_at DESC LIMIT 1
    """, (day_start, day_end))
    row = cur.fetchone()
    if not row:
        print(f"  ERROR: No cron session found for {today}")
        conn.close()
        return

    session_id = row[0]
    print(f"  Session: {session_id}")

    # Get all messages in order
    cur.execute("""
        SELECT id, role, content, tool_name, tool_calls,
               reasoning, reasoning_content, timestamp
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp ASC, id ASC
    """, (session_id,))

    messages = cur.fetchall()
    conn.close()

    # Define phase boundaries based on phase_logger.py tool calls
    # Each boundary is (marker_text_in_tool_output, phase_label)
    boundaries = [
        # Order matters: more specific markers first
        ("phase_logger.py phase5.5-pre", "phase5.5-pre"),
        ("Snapshotted pre-free-roam", "phase5.5-pre"),
        ("phase_logger.py phase3-5", "phase3-5"),
        ("phase3-5.json", "phase3-5"),
        ("phase_logger.py phase5.5 ", "phase5.5"),
        ("phase5.5.json", "phase5.5"),
        ("phase_logger.py phase6", "phase6"),
        ("phase6.json", "phase6"),
        ("phase_logger.py reasoning", "end"),
    ]

    # Find boundary indices
    phase_ranges = []
    current_phase = "phase1-2"
    current_start = 0

    for i, (mid, role, content, tool_name, tool_calls, \
            reasoning, reasoning_content, ts) in enumerate(messages):
        # Check if this is a tool result from a phase_logger.py call.
        # The tool_calls field on the preceding assistant message has the command,
        # but the tool result content has the script output. We match on both:
        # - tool_calls containing "phase_logger.py <phase>" (the command)
        # - tool result content containing "Logged .../<phase>.json" (the output)
        if role == "tool" and tool_name == "terminal":
            text = (content or "")
            # Also check the preceding assistant's tool_calls for the command
            tool_call_text = ""
            if i > 0:
                prev = messages[i - 1]
                if prev[1] == "assistant" and prev[4]:
                    tool_call_text = prev[4]
            combined = text + " " + tool_call_text
            for marker, label in boundaries:
                if marker in combined and label != current_phase:
                    phase_ranges.append((current_phase, current_start, i))
                    current_phase = label
                    current_start = i + 1
                    break

    # Final phase
    phase_ranges.append((current_phase, current_start, len(messages)))

    # Extract reasoning per phase
    for phase_name, start_idx, end_idx in phase_ranges:
        if phase_name == "end":
            continue

        reasoning_parts = []
        tool_count = 0

        for i in range(start_idx, end_idx):
            mid, role, content, tool_name, tool_calls, \
                reasoning, reasoning_content, ts = messages[i]

            if role == "assistant":
                # Model's internal reasoning (thinking tokens)
                if reasoning and reasoning.strip():
                    reasoning_parts.append(f"### Reasoning\n\n{reasoning.strip()}\n")
                # Model's visible text output
                if content and content.strip():
                    reasoning_parts.append(f"### Output\n\n{content.strip()}\n")

            elif role == "tool":
                tool_count += 1
                # Include tool name and truncated output for context
                tool_preview = (content or "")[:200]
                reasoning_parts.append(f"### Tool: {tool_name}\n\n```\n{tool_preview}\n```\n")

        if reasoning_parts:
            log_file = f"{log_dir}/{phase_name}_reasoning.md"
            with open(log_file, "w") as f:
                f.write(f"# Phase: {phase_name}\n\n")
                f.write(f"Messages: {end_idx - start_idx} | Tools: {tool_count}\n\n---\n\n")
                f.write("\n\n".join(reasoning_parts))
            print(f"  Wrote {log_file} ({len(reasoning_parts)} segments, {tool_count} tools)")
        else:
            print(f"  {phase_name}: no reasoning content found")

    # Also write a session summary
    summary = {
        "session_id": session_id,
        "total_messages": len(messages),
        "phases": [
            {"phase": p, "start": s, "end": e, "messages": e - s}
            for p, s, e in phase_ranges if p != "end"
        ],
    }
    with open(f"{log_dir}/session_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Wrote {log_dir}/session_summary.json")


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
    elif phase == "reasoning":
        result = log_reasoning(data_dir, log_dir, today)
        # log_reasoning writes its own files
        return
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
