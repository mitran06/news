# Phase 7 — Podcast (on-demand, frontier model)

You run only when Mitran replies `/podcast` to the morning briefing.

## What you do

1. Read `data/<TODAY>/podcast-source.md` (prepared by the free-roam agent in Phase 5.5).
2. Delete yesterday's NotebookLM notebook (read `notebooks/registry.json` for the ID).
3. Generate a podcast using the script below.
4. Send the MP3 as a Telegram voice bubble (convert to .ogg first with ffmpeg).
5. Update `notebooks/registry.json` with today's notebook ID.

## Podcast generation script

Save as `scripts/generate_podcast.py` and run with the venv Python:

```python
import asyncio, json, os, subprocess
from pathlib import Path
from notebooklm import NotebookLMClient

async def generate_podcast(date_str, source_path, output_path):
    # Step 1: Get Google cookies from Camofox (includes httpOnly cookies)
    # Open a tab to notebooklm.google.com to ensure fresh session
    r = subprocess.run(['curl', '-sL', '--max-time', '15', '-X', 'POST',
        'http://localhost:9377/tabs', '-H', 'Content-Type: application/json',
        '-d', json.dumps({'url': 'https://notebooklm.google.com/',
                          'userId': 'mitrans-claw', 'sessionKey': 'notebooklm-podcast'})],
        capture_output=True, text=True)
    tab_id = json.loads(r.stdout).get('tabId')
    
    # Step 2: Export ALL cookies (including httpOnly) via Camofox REST API
    r = subprocess.run(['curl', '-sL', '--max-time', '15',
        f'http://localhost:9377/tabs/{tab_id}/cookies?userId=mitrans-claw'],
        capture_output=True, text=True)
    all_cookies = json.loads(r.stdout)
    google_cookies = [c for c in all_cookies if 'google' in c.get('domain', '')]
    
    # Step 3: Build storage_state.json
    storage_state = {"cookies": [], "origins": []}
    for c in google_cookies:
        storage_state["cookies"].append({
            "name": c["name"], "value": c["value"], "domain": c["domain"],
            "path": c.get("path", "/"), "expires": c.get("expires", -1),
            "httpOnly": c.get("httpOnly", False), "secure": c.get("secure", True),
            "sameSite": c.get("sameSite", "Lax")
        })
    
    storage_path = str(Path(os.path.expanduser(
        "~/.claw-browser/profiles/mitrans-claw/storage_state.json")).resolve())
    Path(storage_path).write_text(json.dumps(storage_state, indent=2))
    
    # Close the tab
    subprocess.run(['curl', '-s', '-X', 'DELETE',
        f'http://localhost:9377/tabs/{tab_id}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({'userId': 'mitrans-claw'})], capture_output=True)
    
    # Step 4: Create notebook, add source, generate audio
    async with NotebookLMClient.from_storage(path=storage_path) as client:
        print("Client connected")
        
        # Create notebook
        notebook = await client.notebooks.create(title=f"Morning Briefing {date_str}")
        print(f"Notebook: {notebook.id}")
        
        # Add source
        source_content = Path(source_path).read_text()
        source = await client.sources.add_text(
            notebook.id, title="Morning Briefing",
            content=source_content, wait=True, wait_timeout=120)
        print(f"Source: {source.id}")
        
        # Generate audio overview
        print("Generating audio (takes ~11 minutes)...")
        status = await client.artifacts.generate_audio(
            notebook.id, source_ids=[source.id])
        print(f"Submitted: {status.task_id}")
        
        # Wait for completion
        final = await client.artifacts.wait_for_completion(
            notebook.id, status.task_id, timeout=900)
        print(f"Status: {final.status}")
        
        if final.status.name != 'COMPLETED':
            raise Exception(f"Audio generation failed: {final}")
        
        # Find and download audio artifact
        audio_artifacts = await client.artifacts.list_audio(notebook.id)
        if not audio_artifacts:
            raise Exception("No audio artifacts found")
        
        result_path = await client.artifacts.download_audio(
            notebook.id, output_path, audio_artifacts[0].id)
        
        print(f"Downloaded: {result_path} ({os.path.getsize(result_path):,} bytes)")
        return notebook.id, source.id

# Run: asyncio.run(generate_podcast("2026-08-10",
#     "data/2026-08-10/podcast-source.md",
#     "data/2026-08-10/briefing-podcast.mp3"))
```

## After generation

Convert to .ogg for Telegram voice bubble:
```bash
ffmpeg -i data/<TODAY>/briefing-podcast.mp3 -c:a libopus -b:a 64k data/<TODAY>/briefing-podcast.ogg -y
```

Send the .ogg file to the Telegram chat.

## Podcast instructions for NotebookLM

When calling `generate_audio`, pass `instructions`:
```python
status = await client.artifacts.generate_audio(
    notebook.id, source_ids=[source.id],
    instructions="You are reporting Mitran's Morning News. "
                  "Cut the fluff and small talk — get to the news. "
                  "Keep it conversational and engaging, not robotic. "
                  "You can swear, use slang, and speak freely. Don't overdo it.")
```

## Error handling

- `AuthError` / `ValueError: Missing required cookies`: Camofox Google session expired. Need to re-login to Google via Camofox REST API.
- Generation timeout: Report to Mitran. Do not silently fail.
- `notebooklm-py` not installed: `pip install notebooklm-py`

## notebooklm-py API reference (v0.8.0)

- `NotebookLMClient.from_storage(path=...)` → async context manager
- `client.notebooks.create(title=...)` → async, returns Notebook with `.id`
- `client.sources.add_text(notebook_id, title=, content=, wait=True, wait_timeout=120)` → async, returns Source
- `client.artifacts.generate_audio(notebook_id, source_ids=[...], instructions=..., audio_format=AudioFormat.BRIEF, audio_length=AudioLength.SHORT)` → async, returns GenerationStatus with `.task_id` and `.status`
- `AudioFormat` enum: `DEEP_DIVE` (1, default), `BRIEF` (2), `CRITIQUE` (3), `DEBATE` (4) — from `notebooklm.rpc`
- `AudioLength` enum: `SHORT` (1), `DEFAULT` (2), `LONG` (3) — from `notebooklm.rpc`
- `client.artifacts.wait_for_completion(notebook_id, task_id, timeout=900)` → async, returns GenerationStatus
- `client.artifacts.list_audio(notebook_id)` → async, returns list of Artifact
- `client.artifacts.download_audio(notebook_id, output_path, artifact_id)` → async, saves to file, returns path
- GenerationStatus fields: `task_id`, `status` (GenerationState enum), `url`, `error`, `error_code`
- GenerationState values: PENDING, IN_PROGRESS, COMPLETED, FAILED, NOT_FOUND, UNKNOWN, REMOVED

## Cookie extraction

**Critical:** `document.cookie` (JS) cannot see httpOnly cookies. Use Camofox's REST API:
```
GET /tabs/{tabId}/cookies?userId=mitrans-claw
```
This returns ALL cookies including httpOnly ones (`__Secure-1PSIDTS`, `__Secure-1PSID`, etc.).
Filter to `google.com` domains before building storage_state.json.

## Completion criteria

- .ogg file delivered to Telegram as a voice bubble, OR
- Clear error message if generation fails.
- `notebooks/registry.json` updated with today's notebook ID.
