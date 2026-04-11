# A/V Sync Investigation - 2026-04-11

## Current conclusion

- The first root cause is still in the recording stage, not only in `mkv -> mp4`.
- Verified sample:
  - `art_cam__2026-04-11_17-32-02.mkv`
  - `video 1609.600333`
  - `audio 1607.978667`
  - skew about `1.62s` already exists in the source recording.
- After conversion:
  - `art_cam__2026-04-11_17-32-02.mp4`
  - `video 1609.600333`
  - `audio 1608.000000`
  - skew remains about `1.60s`.

## What was changed

- Reverted Chaturbate recording command in [app/platform/chaturbate.py](/Users/chihyi/projects/chaturbate-dvr/app/platform/chaturbate.py:319):
  - removed `--hls-use-mpegts`
  - removed `--downloader ffmpeg`
  - removed `--downloader-args ffmpeg_i:-hide_banner`
- Updated test in [tests/test_chaturbate_platform.py](/Users/chihyi/projects/chaturbate-dvr/tests/test_chaturbate_platform.py:178).
- Kept the earlier salvage logic in [app/services/scheduler/capture.py](/Users/chihyi/projects/chaturbate-dvr/app/services/scheduler/capture.py:15):
  - if recording fails/stops but `.mkv` or `.mkv.part` exists, convert that artifact instead of orphaning it.

## Important observation after rollback

- The rollback is active.
- New live process no longer shows these explicit flags:
  - `--hls-use-mpegts`
  - `--downloader ffmpeg`
- But `yt-dlp` still spawns an `ffmpeg` child for Chaturbate live HLS with separate video/audio playlists.
- New sample after rollback:
  - `art_cam__2026-04-11_18-34-38.mkv.part`
  - `video 49.633333`
  - `audio 49.301333`
  - skew about `0.332s`
- So the rollback did not eliminate drift. It may have reduced the severity versus the `~1.6s` pattern, but the problem still exists.

## Runtime notes

- Interrupted recording was gracefully stopped through `/api/channels/art_cam_/pause`.
- One orphaned `ffmpeg` child had to be terminated manually after the parent `yt-dlp` exited.
- Archived interrupted sample:
  - `/Volumes/Storage/Camrecs/Organized_recs/art_cam_/art_cam__2026-04-11_18-10-10.mp4`
- Original partial retained for comparison:
  - `/Volumes/Storage/Camrecs/videos/art_cam__2026-04-11_18-10-10.mkv.part`

## TODO

- Let the system run for a few days and collect fresh samples after this rollback.
- For any obviously bad recording, keep both files:
  - original `.mkv` or `.mkv.part`
  - converted `.mp4`
- Compare both with `ffprobe` before deleting anything.
- If sync issue still persists, next experiment should focus on format selection:
  - stop using `bestvideo+bestaudio/best`
  - test a single muxed stream first, likely `best`
  - goal: avoid separate live audio/video HLS tracks during recording
- Also inspect whether orphaned child-process cleanup needs a code fix when a recording is paused/stopped.

## Test command used

```bash
./.venv/bin/python -m unittest tests.test_chaturbate_platform tests.test_scheduler_capture tests.test_recorder_service
```

