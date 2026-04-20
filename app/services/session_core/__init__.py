"""Recording session state models, classification, and registry.

This package preserves the historical ``app.services.session_core`` import
surface while splitting the implementation into focused modules.
"""

from __future__ import annotations

from .classify import classify_recording_failure, classify_resolution_failure
from .mappers import (
    domain_failure_category,
    domain_phase,
    domain_status,
    to_domain_resolved_source,
    to_domain_session,
)
from .models import FailureCategory, RecordingPhase, RecordingSession, ResolvedSource
from .registry import RecordingSessionRegistry

__all__ = [
    "FailureCategory",
    "RecordingPhase",
    "RecordingSession",
    "RecordingSessionRegistry",
    "ResolvedSource",
    "classify_recording_failure",
    "classify_resolution_failure",
    "domain_failure_category",
    "domain_phase",
    "domain_status",
    "to_domain_resolved_source",
    "to_domain_session",
]
