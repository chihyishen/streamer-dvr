from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException

from ...services.manual_recording import MissavRecordingService
from ...storage import JsonStore
from ..models import ManualRecordingRequest, ManualRecordingResponse


def register_manual_recording_routes(app: FastAPI, *, store: JsonStore) -> None:
    service = MissavRecordingService()

    @app.post("/api/manual-recordings/missav", response_model=ManualRecordingResponse)
    async def api_start_missav_recording(payload: ManualRecordingRequest = Body(...)):
        try:
            job = service.start(payload.url, store.load_config())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        store.log_info(
            "manual_recording_started",
            "Manual MissAV recording started",
            None,
            url=payload.url,
            pid=job.pid,
            output_path=job.output_path,
            log_path=job.log_path,
        )
        return ManualRecordingResponse(ok=True, pid=job.pid, output_path=job.output_path, log_path=job.log_path)
