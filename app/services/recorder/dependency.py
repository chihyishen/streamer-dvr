from __future__ import annotations

import shutil
from pathlib import Path


class RecorderDependencyMixin:
    def _ensure_dependency(self, binary: str, configured_path: str | None = None) -> str:
        candidate = None
        if configured_path:
            candidate_path = Path(configured_path)
            if not candidate_path.is_absolute():
                candidate_path = Path.cwd() / candidate_path
            if candidate_path.exists():
                candidate = str(candidate_path)
        resolved = candidate or self._resolve_local_binary(binary) or shutil.which(binary)
        if not resolved:
            raise FileNotFoundError(binary)
        return resolved

    def _resolve_local_binary(self, binary: str) -> str | None:
        local_candidates = [
            Path.cwd() / ".venv" / "bin" / binary,
            Path.cwd() / ".venv" / "Scripts" / f"{binary}.exe",
        ]
        for candidate in local_candidates:
            if candidate.exists():
                return str(candidate)
        return None
