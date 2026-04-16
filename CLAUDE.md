# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Streamer DVR is a self-hosted live stream recorder/archiver. Python 3.13 FastAPI backend + Vue 3 frontend. Records via ffmpeg directly from resolved HLS source URLs, remuxes with ffmpeg, persists to SQLite (events/sessions) and JSON (channels/config). yt-dlp is retained as a probe fallback when the API resolver fails. Currently supports Chaturbate with a multi-platform adapter pattern.

## Common Commands

### Backend
```bash
# Install dependencies
python -m pip install -r requirements.txt

# Run API server
python -m app.main

# Run worker (scheduler/recorder)
python -m app.worker

# Run all tests
python -m unittest discover -s tests

# Run a single test file
python -m unittest tests.test_chaturbate_platform

# Run a single test method
python -m unittest tests.test_chaturbate_platform.ChaturbatePlatformTests.test_build_record_command_uses_yt_dlp_defaults_and_consistent_headers

# Compile check (same as CI)
python -m compileall app scripts
```

### Frontend
```bash
cd frontend
npm ci
npm run dev          # Dev server on :5173, proxies API to :8787
npm run build        # Production build to frontend/dist/
```

### Production (PM2)
```bash
pm2 start ecosystem.config.js
```

## Architecture

### Two Processes
- **API** (`app.main`): FastAPI server on port 8787. Serves REST API + built Vue SPA from `frontend/dist/`.
- **Worker** (`app.worker`): Runs `SchedulerService` loop — probes channels, launches recordings, handles recovery.

### Service Layer (`app/services/`)
Services use **mixin-based composition**. `RecorderService` inherits from `RecorderPathMixin`, `RecorderProbeMixin`, `RecorderDependencyMixin`. `SchedulerService` inherits from capture, probe, recovery, and commands mixins.

- **SchedulerService**: Main loop that probes channels on interval, starts recordings, detects stalled processes, runs retention pruning.
- **RecorderService**: Resolves stream sources, builds ffmpeg direct-recording and remux commands, classifies failures. yt-dlp is used as a probe fallback when API resolution fails.
- **ChannelService / ConfigService**: CRUD for channels and app config.
- **RecordingSessionRegistry** (`session_core.py`): State machine tracking recording lifecycle phases (PROBING → RESOLVING_SOURCE → RECORDING → CONVERTING → COMPLETED/FAILED).

### Platform Adapter Pattern (`app/platform/`)
`PlatformAdapter` abstract base with methods: `resolve_stream_source()`, `build_record_command()`, `build_record_command_for_source()`, `map_recording_failure()`. `ChaturbatePlatform` is the concrete implementation. `PlatformRegistry` maps `Platform` enum to adapters.

### Recording Pipeline
1. **Probe**: Scheduler checks if streamer is live via API (`/api/chatvideocontext/`)
2. **Record**: Spawns ffmpeg subprocess recording from resolved HLS source URL to `.mkv`
3. **Convert**: Remuxes `.mkv` → `.mp4` with `ffmpeg -c copy -movflags faststart`
4. **Recovery**: Handles stalled recordings (no file growth for 180s), orphaned processes, partial `.mkv.part` files

### Storage (`app/storage/`)
- `SQLiteStore`: Events, recording sessions, command queue
- `JsonStore` (extends SQLiteStore): Channels and config stored as JSON files
- Bootstrap API endpoint sends full app state (channels + config + recent events) to frontend

### Domain Models (`app/domain/`)
Key enums: `Status` (IDLE/CHECKING/RECORDING/PAUSED/ERROR), `ErrorCode`, `FailureCategory`, `RecordingSessionPhase`. Channel model includes optional `max_resolution`, `max_framerate`, `filename_pattern`.

### API Routes (`app/api/routes/`)
Organized by resource: bootstrap, channels, logs, settings, health.

## Testing
- Framework: **unittest** (not pytest)
- All tests use `unittest.mock` for isolation
- Tests are in `tests/` directory, one file per service/component
- No linter configured in CI — CI only runs `python -m compileall`
