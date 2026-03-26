# Streamer DVR

A self-hosted, automated live stream recorder and archiver, built with Python (FastAPI) and Vue 3.

**Currently optimized for Chaturbate, with a modular architecture designed for multi-platform expansion.**

## Features

- **Automated Monitoring**: Continuously polls streamers and starts recording as soon as they go live.
- **Smart Archiving**: Records in high-quality `mkv` and automatically remuxes to `mp4` for maximum compatibility.
- **Web Dashboard**: Clean, modern UI to manage channels, view logs, and monitor recording status in real-time.
- **Multi-Platform Ready**: Architected with a registry/adapter pattern to easily add new streaming platforms.
- **Configurable Polling**: Set custom check intervals per streamer to balance responsiveness and resource usage.
- **Robust Recovery**: Automatically recovers and resumes tracking if the service restarts during an active stream.
- **Organized Storage**: Automatically moves finished recordings into structured directories by streamer name.

## Supported Platforms

- [x] **Chaturbate**: Full support (monitoring, recording, session/cookie sync).
- [ ] **Future Expansion**: Support for other major live platforms is planned via a modular adapter system.

## Architecture

- **Backend**: FastAPI (Python 3.13)
- **Worker**: Multi-threaded scheduler and recorder process
- **Frontend**: Vue 3 + Vite
- **Core Tools**: `yt-dlp` for stream capture, `ffmpeg` for remuxing
- **Persistence**: SQLite (Events) + JSON (Channels & Config)

## Prerequisites

- Python 3.13+
- Node.js 20+
- `ffmpeg` installed on the host system and available in `PATH`
- `pm2` (recommended for production deployment)

## Quick Start

### 1. Clone and Install

```bash
# Backend setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend setup
npm install --prefix frontend
```

### 2. Configuration

On first start the app will create `config.json` and `channels.json` automatically.
If you want to customize paths up front, copy the example config and edit it before launching:

```bash
cp config.json.example config.json
```

Key settings in `config.json`:
- `recordings_dir`: Temporary space for active recordings.
- `organized_dir`: Final archive directory.
- `ffmpeg_path`: Path to your `ffmpeg` executable. Host installation is still required.
- `yt_dlp_path`: Optional explicit path to `yt-dlp`. If omitted or invalid, the app will try `.venv/bin/yt-dlp`, `.venv/Scripts/yt-dlp.exe`, then `PATH`.

### 3. Run

#### Development Mode

Development keeps the Vite dev server for fast iteration and hot reload:

```bash
# Terminal 1: API
python -m app.main

# Terminal 2: Worker
python -m app.worker

# Terminal 3: Frontend Dev
npm run dev --prefix frontend
```

Open the dashboard at `http://127.0.0.1:5173`.

> **Note**: If you change the backend port in `config.json` (default 8787), you must also update the proxy target in `frontend/vite.config.ts` for development mode.

#### Production Mode

In production, FastAPI serves the built frontend from `frontend/dist`, so you only need two long-running processes: the API and the worker.

```bash
npm run build --prefix frontend
./scripts/pm2-start.sh
```

Open the dashboard at `http://127.0.0.1:8787`.

### System Dependencies

`yt-dlp` is installed via Python dependencies and auto-detected from the local virtual environment when available.
`ffmpeg` must be installed separately on the host:

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt-get update
sudo apt-get install -y ffmpeg
```

Quick verification:

```bash
ffmpeg -version
.venv/bin/yt-dlp --version
```

## Project Structure

- `app/`: Core backend logic and services.
- `frontend/`: Vue 3 dashboard source code.
- `scripts/`: Deployment and maintenance utilities.
- `.internal/`: (Ignored) Design documents and private notes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Deployment Notes

- Development mode uses the Vite dev server on port `5173` and proxies API requests to `8787`.
- Production mode serves the built dashboard from FastAPI on port `8787`.
- PM2 should manage only the API and worker processes. The frontend is built ahead of time and served by the backend.
- Docker is not required for the default deployment path yet. The current recommended setup is a host install with explicit data directories and host-level `ffmpeg`.

## Cookie Synchronization (macOS)

For many platforms, valid session cookies are required for recording.

### Automatic Sync
Run the provided script to extract cookies from your local browser (Edge, Chrome, etc.):

```bash
python scripts/sync_cookies.py
```

### Important: macOS Security

When running for the first time, you may see a macOS "KeyChain Access" prompt.
1. Ensure your terminal has permission to access your browser's data.
2. Click **"Always Allow"** in the KeyChain prompt to avoid being asked every time.
3. The script will generate `streamer_cookies.txt` (Netscape format), which is used by `yt-dlp`.
