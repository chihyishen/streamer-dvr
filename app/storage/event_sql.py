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

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_events_channel_timestamp ON events(channel_id, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_events_type_timestamp ON events(event_type, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_events_level_timestamp ON events(level, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_commands_pending ON commands(completed_at, claimed_at, created_at)",
]
