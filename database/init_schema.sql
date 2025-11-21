-- Database schema with new event_tasks table for task-based execution
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_event_name TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    event_json TEXT,
    description TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    event_in_progress INTEGER DEFAULT 0,
    event_started INTEGER DEFAULT 0,
    event_over INTEGER DEFAULT 0,
    last_scoreboard_time TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    scoreboard_interval INTEGER DEFAULT 600
);

CREATE TABLE IF NOT EXISTS event_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    task_name TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    priority INTEGER NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT 0,
    execution_length_ms INTEGER DEFAULT 0,
    completed_time TEXT NULL,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_event_tasks_schedule ON event_tasks(completed, scheduled_time, priority);

CREATE TABLE IF NOT EXISTS event_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL,
    sent_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    UNIQUE(event_id, notification_type)
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    message TEXT NOT NULL,
    log_level TEXT DEFAULT 'INFO'
);

CREATE TABLE IF NOT EXISTS event_winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    final_score INTEGER,
    was_online BOOLEAN DEFAULT TRUE,
    rewarded_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

-- Triggers for timestamp validation
CREATE TRIGGER IF NOT EXISTS enforce_events_times_insert
BEFORE INSERT ON events
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.start_time IS NOT NULL
             AND NEW.start_time NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'start_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
    SELECT CASE
        WHEN NEW.end_time IS NOT NULL
             AND NEW.end_time NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'end_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_events_times_update
BEFORE UPDATE ON events
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.start_time IS NOT NULL
             AND NEW.start_time NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'start_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
    SELECT CASE
        WHEN NEW.end_time IS NOT NULL
             AND NEW.end_time NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'end_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_tasks_times_insert
BEFORE INSERT ON event_tasks
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.scheduled_time IS NOT NULL
             AND NEW.scheduled_time NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'scheduled_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_tasks_times_update
BEFORE UPDATE ON event_tasks
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.scheduled_time IS NOT NULL
             AND NEW.scheduled_time NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'scheduled_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
    SELECT CASE
        WHEN NEW.completed_time IS NOT NULL
             AND NEW.completed_time NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'completed_time must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_notifications_insert
BEFORE INSERT ON event_notifications
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.sent_at IS NOT NULL
             AND NEW.sent_at NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'sent_at must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_notifications_update
BEFORE UPDATE ON event_notifications
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.sent_at IS NOT NULL
             AND NEW.sent_at NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'sent_at must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_logs_insert
BEFORE INSERT ON logs
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.timestamp IS NOT NULL
             AND NEW.timestamp NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'timestamp must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_logs_update
BEFORE UPDATE ON logs
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.timestamp IS NOT NULL
             AND NEW.timestamp NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'timestamp must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_winners_insert
BEFORE INSERT ON event_winners
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.rewarded_at IS NOT NULL
             AND NEW.rewarded_at NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'rewarded_at must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_winners_update
BEFORE UPDATE ON event_winners
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.rewarded_at IS NOT NULL
             AND NEW.rewarded_at NOT LIKE '____-__-__T__:__:__Z'
        THEN RAISE (ABORT, 'rewarded_at must be UTC in YYYY-MM-DDTHH:MM:SSZ format')
    END;
END;