from __future__ import annotations

SCHEMA_VERSION = 1

SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""

CHANNELS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""

EVENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    channel_id TEXT,
    message TEXT NOT NULL,
    metadata_json TEXT NOT NULL
)
"""

COMMAND_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    type TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    claimed_at TEXT,
    completed_at TEXT
)
"""

SESSION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS recording_sessions (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL,
    current_phase TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    last_heartbeat_at TEXT,
    active_pid INTEGER,
    active_resolved_source_id TEXT,
    final_failure_category TEXT,
    final_failure_message TEXT,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(active_resolved_source_id) REFERENCES resolved_sources(id) ON DELETE SET NULL
)
"""

RESOLVED_SOURCE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS resolved_sources (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    resolver_tool TEXT NOT NULL,
    candidate_index INTEGER NOT NULL,
    candidate_url TEXT,
    stream_url TEXT,
    room_status TEXT,
    auth_mode TEXT NOT NULL,
    source_variant TEXT,
    source_fingerprint TEXT,
    validated_at TEXT,
    expires_at TEXT,
    message TEXT,
    raw_output TEXT,
    return_code INTEGER,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES recording_sessions(id) ON DELETE CASCADE
)
"""

SESSION_EVENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    phase TEXT NOT NULL,
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    failure_category TEXT,
    message TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES recording_sessions(id) ON DELETE CASCADE
)
"""

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_events_channel_timestamp ON events(channel_id, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_events_type_timestamp ON events(event_type, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_events_level_timestamp ON events(level, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_commands_pending ON commands(completed_at, claimed_at, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_channel_updated ON recording_sessions(channel_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status_updated ON recording_sessions(status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_phase_updated ON recording_sessions(current_phase, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_resolved_sources_session ON resolved_sources(session_id, candidate_index ASC)",
    "CREATE INDEX IF NOT EXISTS idx_session_events_session_time ON session_events(session_id, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_session_events_phase_time ON session_events(phase, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_session_events_failure_time ON session_events(failure_category, timestamp DESC)",
]
